# services/domain_verification.py
import os

import dns.resolver
import dns.exception
import logging
import requests
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.cache import cache

from .ssl_provisioning_service import SSLProvisioningService
from .nginx_config_service import NginxConfigService
from django.core.cache import cache

from Qr.models import CustomDomain

logger = logging.getLogger(__name__)


class DomainVerificationService:
    """Service for verifying custom domains"""

    def __init__(self):
        self.resolver = dns.resolver.Resolver(configure=False)
        self.resolver.nameservers = settings.DNS_NAMESERVERS if hasattr(settings, 'DNS_NAMESERVERS') else [
            "1.1.1.1",  # Cloudflare
            "8.8.8.8",  # Google
            "9.9.9.9",  # Quad9
        ]
        self.resolver.timeout = 5
        self.resolver.lifetime = 10

        self.expected_ip = settings.CUSTOM_DOMAIN_IP
        self.expected_cname = self.normalize_domain(
            getattr(settings, "CUSTOM_DOMAIN_CNAME_TARGET", "")
        )

        # Cache for DNS lookups
        self.dns_cache_ttl = 300  # 5 minutes

    def normalize_domain(self, domain: str) -> str:
        """Normalize domain string"""
        if not domain:
            return domain
        return domain.strip().lower().rstrip(".")

    def get_a_records(self, domain: str, use_cache: bool = True) -> List[str]:
        domain = self.normalize_domain(domain)
        cache_key = f"dns_a_{domain}"

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            answers = self.resolver.resolve(
                domain,
                "A",
                raise_on_no_answer=True
            )

            records = [
                answer.address
                for answer in answers
            ]

            if use_cache:
                cache.set(
                    cache_key,
                    records,
                    self.dns_cache_ttl
                )

            return records

        except (
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers,
                dns.resolver.Timeout,
        ):
            return []

        except Exception as e:
            logger.error(
                f"Error resolving A record for {domain}: {e}"
            )
            return []

    def get_txt_records(self, domain: str) -> List[str]:
        """Get TXT records for a domain"""
        domain = self.normalize_domain(domain)
        cache_key = f"dns_txt_{domain}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            answers = self.resolver.resolve(
                domain,
                "TXT",
                raise_on_no_answer=True
            )

            records = []
            for answer in answers:
                records.extend([str(r).strip('"') for r in answer.strings])

            if records:
                cache.set(cache_key, records, self.dns_cache_ttl)

            return records

        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception as e:
            logger.error(f"Error resolving TXT for {domain}: {str(e)}")
            return []

    def get_cname_records(self, domain: str, use_cache: bool = True) -> List[str]:
        """Get CNAME records for a domain"""
        domain = self.normalize_domain(domain)
        cache_key = f"dns_cname_{domain}"

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            answers = self.resolver.resolve(
                domain,
                "CNAME",
                raise_on_no_answer=True,
            )

            records = [
                self.normalize_domain(str(answer.target).rstrip("."))
                for answer in answers
            ]

            if use_cache:
                cache.set(cache_key, records, self.dns_cache_ttl)

            return records

        except (
            dns.resolver.NoAnswer,
            dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers,
            dns.resolver.Timeout,
        ):
            return []
        except Exception as e:
            logger.error(f"Error resolving CNAME for {domain}: {str(e)}")
            return []

    def verify_cname_record(self, domain: str) -> bool:
        domain = self.normalize_domain(domain)
        if not self.expected_cname:
            return False

        records = self.get_cname_records(domain)
        return self.expected_cname in records

    def verify_txt(self, domain: str, token: str) -> bool:
        """Verify TXT record contains verification token"""
        domain = self.normalize_domain(domain)
        records = self.get_txt_records(domain)

        expected = f"domain-verify={token}"
        return any(expected in record for record in records)

    def verify_http(self, domain: str) -> bool:
        """Verify the domain serves the frontend over HTTP/HTTPS"""
        domain = self.normalize_domain(domain)
        verification_path = "/"

        try:
            # Try HTTPS first
            url = f"https://{domain}{verification_path}"
            response = requests.get(url, timeout=5, verify=True)

            if response.status_code == 200:
                return True

            # Fallback to HTTP
            url = f"http://{domain}{verification_path}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                return True

            return False

        except requests.exceptions.RequestException as e:
            logger.info(f"HTTP verification failed for {domain}: {str(e)}")
            return False

    def verify_domain(self, domain_instance) -> Dict[str, Any]:
        """Verify that the custom domain points to the configured frontend domain."""
        if isinstance(domain_instance, str):
            try:
                domain_instance = CustomDomain.objects.get(domain=domain_instance)
            except CustomDomain.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Domain not found'
                }

        domain = self.normalize_domain(domain_instance.domain)
        # Update status to verifying
        domain_instance.status = CustomDomain.Status.VERIFYING
        domain_instance.verification_attempts += 1
        domain_instance.last_verification_attempt = timezone.now()
        domain_instance.save()

        verification_results = {
            'cname': self.verify_cname_record(domain),
            'expected_cname': self.expected_cname,
        }

        is_verified = verification_results['cname']

        if is_verified:
            domain_instance.status = CustomDomain.Status.VERIFIED
            domain_instance.verified_at = timezone.now()
            domain_instance.save()

            return {
                'success': True,
                'message': 'Domain CNAME verified successfully',
                'domain': domain,
                'method': 'cname',
                'verification_results': verification_results
            }
        else:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.save()

            return {
                'success': False,
                'message': 'DNS verification failed. Please check your CNAME record.',
                'domain': domain,
                'attempts': domain_instance.verification_attempts,
                'verification_results': verification_results
            }

    def auto_verify_pending_domains(self, max_attempts: int = 5) -> Dict[str, Any]:
        """Auto-verify pending domains"""

        # Find pending domains that need verification
        pending_domains = CustomDomain.objects.filter(
            status__in=[CustomDomain.Status.PENDING, CustomDomain.Status.VERIFYING],
            verification_attempts__lt=max_attempts,
            is_deleted=False
        )

        # Filter by last attempt time (don't re-verify too frequently)
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        pending_domains = pending_domains.filter(
            models.Q(last_verification_attempt__isnull=True) |
            models.Q(last_verification_attempt__lt=one_hour_ago)
        )

        results = []
        for domain in pending_domains:
            result = self.verify_domain(domain)
            results.append(result)

        return {
            'success': True,
            'processed': len(results),
            'results': results
        }

    # services/domain_verification.py

    def verify_and_activate_domain(self, domain_instance):
        # Step 1: DNS verification (keep as is)
        dns_result = self.verify_domain(domain_instance)
        if not dns_result['success']:
            return dns_result

        # Update status
        domain_instance.status = CustomDomain.Status.VERIFIED
        domain_instance.dns_verified_at = timezone.now()
        domain_instance.save()

        # Step 2: Write HTTP-only Nginx config FIRST
        nginx_service = NginxConfigService(domain_instance)
        # Use context to set root (ensure your domain root exists)
        root_path = f"/var/www/qrpac"
        nginx_result = nginx_service.write_config(context={'root': root_path})
        if not nginx_result['success']:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.automation_error = nginx_result.get('error')
            domain_instance.save()
            return {'success': False, 'step': 'nginx_write', 'error': nginx_result.get('error')}

        # Enable and reload Nginx (HTTP now serves the domain)
        enable_result = nginx_service.enable_site()
        if not enable_result['success']:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.automation_error = enable_result.get('error')
            domain_instance.save()
            return {'success': False, 'step': 'nginx_enable', 'error': enable_result.get('error')}

        reload_result = NginxConfigService.full_nginx_reload()
        if not reload_result['success']:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.automation_error = reload_result.get('error')
            domain_instance.save()
            return {'success': False, 'step': 'nginx_reload', 'error': reload_result.get('error')}

        # Step 3: Provision SSL using webroot
        ssl_service = SSLProvisioningService(domain_instance.domain)
        ssl_result = ssl_service.provision_certificate_webroot(root_path)
        if not ssl_result['success']:
            domain_instance.status = CustomDomain.Status.SSL_PENDING
            domain_instance.automation_error = ssl_result.get('error')
            domain_instance.save()
            return {
                'success': False,
                'step': 'ssl_provisioning',
                'error': ssl_result.get('error')
            }

        # Update SSL fields
        domain_instance.ssl_verified = True
        domain_instance.ssl_verified_at = timezone.now()
        domain_instance.ssl_issued_at = timezone.now()
        domain_instance.ssl_expires_at = ssl_result.get('expires_at')  # you may need to parse from cert output
        domain_instance.save()

        # Step 4: Rewrite Nginx config with SSL (use the template with SSL directives)
        # We'll use the updated NginxConfigService that includes SSL in template
        # But we need to pass the SSL context (or just rely on the template)
        ssl_nginx_result = nginx_service.write_config(
            context={
                'root': root_path,
                'ssl_enabled': True,
            }
        )
        if not ssl_nginx_result['success']:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.automation_error = ssl_nginx_result.get('error')
            domain_instance.save()
            return {'success': False, 'step': 'nginx_ssl_write', 'error': ssl_nginx_result.get('error')}

        # Reload Nginx again (now with SSL)
        reload_result = NginxConfigService.full_nginx_reload()
        if not reload_result['success']:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.automation_error = reload_result.get('error')
            domain_instance.save()
            return {'success': False, 'step': 'nginx_reload_ssl', 'error': reload_result.get('error')}

        # Step 5: Mark as Active
        domain_instance.status = CustomDomain.Status.ACTIVE
        domain_instance.activated_at = timezone.now()
        domain_instance.nginx_configured_at = timezone.now()
        domain_instance.nginx_enabled = True
        domain_instance.nginx_config_path = nginx_service.config_path
        domain_instance.save()

        return {
            'success': True,
            'message': f'Domain {domain_instance.domain} is now active with SSL!',
            'domain': domain_instance.domain,
            'status': domain_instance.status,
            'ssl_verified': domain_instance.ssl_verified,
            'nginx_configured': True
        }

    def deactivate_domain(self, domain_instance):
        """Deactivate domain and remove Nginx config"""

        # Remove Nginx configuration
        nginx_service = NginxConfigService(domain_instance)

        # Disable site
        nginx_service.disable_site()

        # Remove config file
        nginx_service.remove_config()

        # Reload Nginx
        NginxConfigService.full_nginx_reload()

        # Update domain status
        domain_instance.status = CustomDomain.Status.DISABLED
        domain_instance.nginx_enabled = False
        domain_instance.save()

        return {
            'success': True,
            'message': f'Domain {domain_instance.domain} has been deactivated'
        }

    def cleanup_domain_assets(self, domain_instance):
        """Remove Nginx and SSL assets created for a custom domain."""
        nginx_service = NginxConfigService(domain_instance)
        ssl_service = SSLProvisioningService(domain_instance.domain)

        nginx_result = nginx_service.cleanup_site()
        reload_result = {'success': True, 'message': 'Nginx reload skipped'}
        if nginx_result.get('success'):
            reload_result = NginxConfigService.full_nginx_reload()

        ssl_result = ssl_service.delete_certificate()

        success = (
            nginx_result.get('success')
            and reload_result.get('success')
            and ssl_result.get('success')
        )
        errors = []
        if not nginx_result.get('success'):
            errors.extend(nginx_result.get('errors') or [nginx_result.get('error', 'Nginx cleanup failed')])
        if not reload_result.get('success'):
            errors.append(reload_result.get('error', 'Nginx reload failed'))
        if not ssl_result.get('success'):
            errors.append(ssl_result.get('error', 'SSL cleanup failed'))

        return {
            'success': success,
            'domain': domain_instance.domain,
            'nginx': nginx_result,
            'nginx_reload': reload_result,
            'ssl': ssl_result,
            'errors': errors,
        }

    def get_domain_status(self, domain):
        """Get detailed domain status"""
        try:
            domain_obj = CustomDomain.objects.get(domain=domain)
            nginx_service = NginxConfigService(domain_obj)

            return {
                'domain': domain,
                'status': domain_obj.status,
                'is_active': domain_obj.status == CustomDomain.Status.ACTIVE,
                'ssl_verified': domain_obj.ssl_verified,
                'ssl_expires_at': domain_obj.ssl_expires_at,
                'nginx_configured': domain_obj.nginx_enabled,
                'nginx_config_exists': os.path.exists(nginx_service.config_path),
                'nginx_enabled_exists': os.path.exists(nginx_service.enabled_path),
                'created_at': domain_obj.created_at,
                'activated_at': domain_obj.activated_at
            }
        except CustomDomain.DoesNotExist:
            return {
                'domain': domain,
                'exists': False
            }

    def clear_dns_cache(self, domain: Optional[str] = None):
        """Clear DNS cache for a specific domain or all domains"""
        if domain:
            cache.delete(f"dns_a_{domain}")
            cache.delete(f"dns_cname_{domain}")
            cache.delete(f"dns_txt_{domain}")
        else:
            # Clear all domain caches (use with caution)
            cache.delete_pattern("dns_*")


def normalize_domain(domain: str) -> str:
    """Helper function to normalize domain"""
    if not domain:
        return domain
    return domain.strip().lower().rstrip(".")


"""
1. Go to your DNS provider's control panel
2. Add the following CNAME record:
   - Type: CNAME
   - Host: {obj.domain}
   - Value: {settings.CUSTOM_DOMAIN_CNAME_TARGET}
   - TTL: 3600

3. (Optional) Add TXT record for additional verification:
   - Type: TXT
   - Host: {obj.domain}
   - Value: domain-verify={obj.verification_token}

4. Click the verification link below after DNS propagation
   (may take up to 24 hours)
            """,
