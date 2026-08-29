# services/ssl_provisioning_service.py
import subprocess
import os
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class SSLProvisioningService:
    """Service for provisioning SSL certificates via Let's Encrypt"""

    def __init__(self, domain):
        self.domain = domain
        self.email = getattr(settings, 'LETSENCRYPT_EMAIL', 'admin@yourdomain.com')

    def provision_certificate(self, test_mode=False):
        """Provision SSL certificate using Certbot"""
        try:
            # Build Certbot command
            cmd = [
                'certbot', 'certonly', '--nginx',
                '-d', self.domain,
                '--non-interactive',
                '--agree-tos',
                '--email', self.email,
                '--keep-until-expiring'
            ]

            if test_mode:
                cmd.append('--test-cert')

            logger.info(f"Running Certbot for {self.domain}: {' '.join(cmd)}")

            # Run Certbot
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                cert_path = f"/etc/letsencrypt/live/{self.domain}/fullchain.pem"
                key_path = f"/etc/letsencrypt/live/{self.domain}/privkey.pem"

                # Verify certificates exist
                if os.path.exists(cert_path) and os.path.exists(key_path):
                    logger.info(f"SSL certificate provisioned for {self.domain}")
                    return {
                        'success': True,
                        'cert_path': cert_path,
                        'key_path': key_path,
                        'output': result.stdout,
                        'expires_at': self._get_cert_expiry(cert_path)
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Certificate files not found after provisioning',
                        'output': result.stdout,
                        'stderr': result.stderr
                    }
            else:
                logger.error(f"Certbot failed for {self.domain}: {result.stderr}")
                return {
                    'success': False,
                    'error': result.stderr,
                    'output': result.stdout
                }

        except subprocess.TimeoutExpired:
            logger.error(f"Certbot timeout for {self.domain}")
            return {
                'success': False,
                'error': 'SSL provisioning timed out'
            }
        except Exception as e:
            logger.error(f"SSL provisioning error for {self.domain}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _get_cert_expiry(self, cert_path):
        """Get certificate expiration date"""
        try:
            cmd = [
                'openssl', 'x509', '-in', cert_path,
                '-enddate', '-noout'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Parse expiry date
                expiry_str = result.stdout.strip().replace('notAfter=', '')
                from datetime import datetime
                return datetime.strptime(expiry_str, '%b %d %H:%M:%S %Y %Z')
            return None
        except Exception:
            return None

    def renew_certificate(self):
        """Renew existing certificate"""
        try:
            cmd = ['certbot', 'renew', '--non-interactive']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return {'success': True, 'output': result.stdout}
            else:
                return {'success': False, 'error': result.stderr}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def revoke_certificate(self):
        """Revoke certificate"""
        try:
            cmd = ['certbot', 'revoke', '--cert-path', f'/etc/letsencrypt/live/{self.domain}/fullchain.pem']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return {'success': True, 'output': result.stdout}
            else:
                return {'success': False, 'error': result.stderr}
        except Exception as e:
            return {'success': False, 'error': str(e)}