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

        self.cname_target = normalize_domain(settings.CUSTOM_DOMAIN_CNAME_TARGET)

        # Cache for DNS lookups
        self.dns_cache_ttl = 300  # 5 minutes

    def normalize_domain(self, domain: str) -> str:
        """Normalize domain string"""
        if not domain:
            return domain
        return domain.strip().lower().rstrip(".")

    def get_cname_records(self, domain: str, use_cache: bool = True) -> List[str]:
        """Get CNAME records for a domain with caching"""
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
                raise_on_no_answer=True
            )

            records = [
                self.normalize_domain(str(answer.target))
                for answer in answers
            ]

            # Cache results
            if use_cache:
                cache.set(cache_key, records, self.dns_cache_ttl)

            return records

        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            logger.info(f"No CNAME record found for {domain}")
            return []
        except dns.resolver.NoNameservers:
            logger.error(f"No nameservers available for {domain}")
            return []
        except dns.resolver.Timeout:
            logger.error(f"DNS timeout for {domain}")
            return []
        except Exception as e:
            logger.error(f"Error resolving CNAME for {domain}: {str(e)}")
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

    def verify_cname(self, domain: str) -> bool:
        """Verify CNAME record matches expected target"""
        domain = self.normalize_domain(domain)
        records = self.get_cname_records(domain)
        return self.cname_target in records

    def verify_txt(self, domain: str, token: str) -> bool:
        """Verify TXT record contains verification token"""
        domain = self.normalize_domain(domain)
        records = self.get_txt_records(domain)

        expected = f"domain-verify={token}"
        return any(expected in record for record in records)

    def verify_http(self, domain: str) -> bool:
        """Verify domain through HTTP endpoint"""
        domain = self.normalize_domain(domain)
        verification_path = "/.well-known/domain-verify"

        try:
            # Try HTTPS first
            url = f"https://{domain}{verification_path}"
            response = requests.get(url, timeout=5, verify=True)

            if response.status_code == 200:
                data = response.json()
                return data.get('verified', False)

            # Fallback to HTTP
            url = f"http://{domain}{verification_path}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return data.get('verified', False)

            return False

        except requests.exceptions.RequestException as e:
            logger.info(f"HTTP verification failed for {domain}: {str(e)}")
            return False

    def verify_domain(self, domain_instance) -> Dict[str, Any]:
        """Verify domain using multiple methods"""
        if isinstance(domain_instance, str):
            try:
                domain_instance = CustomDomain.objects.get(domain=domain_instance)
            except CustomDomain.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Domain not found'
                }

        domain = self.normalize_domain(domain_instance.domain)
        token = domain_instance.verification_token

        # Update status to verifying
        domain_instance.status = CustomDomain.Status.VERIFYING
        domain_instance.verification_attempts += 1
        domain_instance.last_verification_attempt = timezone.now()
        domain_instance.save()

        # Try multiple verification methods
        verification_results = {
            'cname': self.verify_cname(domain),
            'txt': self.verify_txt(domain, token),
            'http': self.verify_http(domain)
        }

        # Consider verified if any method succeeds
        is_verified = any(verification_results.values())

        if is_verified:
            domain_instance.status = CustomDomain.Status.ACTIVE
            domain_instance.verified_at = timezone.now()
            domain_instance.activated_at = timezone.now()
            domain_instance.save()

            return {
                'success': True,
                'message': 'Domain verified successfully',
                'domain': domain,
                'method': next((k for k, v in verification_results.items() if v), 'unknown'),
                'verification_results': verification_results
            }
        else:
            domain_instance.status = CustomDomain.Status.FAILED
            domain_instance.save()

            return {
                'success': False,
                'message': 'DNS verification failed. Please check your DNS records.',
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

    def verify_and_activate_domain(self, domain_instance):
        """Full verification and activation pipeline"""

        # Step 1: DNS Verification (your existing method)
        dns_result = self.verify_domain(domain_instance)

        if not dns_result['success']:
            return dns_result

        # Update status to DNS verified
        domain_instance.status = CustomDomain.Status.VERIFIED
        domain_instance.dns_verified_at = timezone.now()
        domain_instance.save()

        # Step 2: SSL Provisioning
        ssl_service = SSLProvisioningService(domain_instance.domain)
        ssl_result = ssl_service.provision_certificate()

        if not ssl_result['success']:
            domain_instance.status = CustomDomain.Status.SSL_PENDING
            domain_instance.automation_error = ssl_result.get('error', 'SSL provisioning failed')
            domain_instance.save()
            return {
                'success': False,
                'step': 'ssl_provisioning',
                'error': ssl_result.get('error', 'SSL provisioning failed'),
                'ssl_details': ssl_result
            }

        # Update SSL fields
        domain_instance.ssl_verified = True
        domain_instance.ssl_verified_at = timezone.now()
        domain_instance.ssl_issued_at = timezone.now()
        domain_instance.ssl_expires_at = ssl_result.get('expires_at')
        domain_instance.status = CustomDomain.Status.SSL_PENDING
        domain_instance.save()

        # Step 3: Nginx Configuration
        nginx_service = NginxConfigService(domain_instance)
        nginx_result = nginx_service.write_config()

        if not nginx_result['success']:
            domain_instance.status = CustomDomain.Status.NGINX_PENDING
            domain_instance.automation_error = nginx_result.get('error', 'Nginx config failed')
            domain_instance.save()
            return {
                'success': False,
                'step': 'nginx_configuration',
                'error': nginx_result.get('error', 'Nginx config failed')
            }

        # Enable site
        enable_result = nginx_service.enable_site()
        if not enable_result['success']:
            domain_instance.status = CustomDomain.Status.NGINX_PENDING
            domain_instance.automation_error = enable_result.get('error', 'Nginx enable failed')
            domain_instance.save()
            return {
                'success': False,
                'step': 'nginx_enable',
                'error': enable_result.get('error', 'Nginx enable failed')
            }

        # Reload Nginx
        reload_result = NginxConfigService.full_nginx_reload()
        if not reload_result['success']:
            domain_instance.status = CustomDomain.Status.NGINX_PENDING
            domain_instance.automation_error = reload_result.get('error', 'Nginx reload failed')
            domain_instance.save()
            return {
                'success': False,
                'step': 'nginx_reload',
                'error': reload_result.get('error', 'Nginx reload failed')
            }

        # Step 4: Mark as Active
        domain_instance.status = CustomDomain.Status.ACTIVE
        domain_instance.activated_at = timezone.now()
        domain_instance.nginx_configured_at = timezone.now()
        domain_instance.nginx_enabled = True
        domain_instance.nginx_config_path = nginx_service.config_path
        domain_instance.save()

        # Clear caches
        cache.delete_pattern(f"verified_domain_*")

        return {
            'success': True,
            'message': f'Domain {domain_instance.domain} is now active!',
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