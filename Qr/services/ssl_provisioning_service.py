# services/ssl_provisioning_service.py
import os
import shutil
import subprocess
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


LETSENCRYPT_ROOT = Path('/etc/letsencrypt')


class SSLProvisioningService:
    def __init__(self, domain):
        self.domain = domain
        self.email = getattr(settings, 'LETSENCRYPT_EMAIL', 'admin@yourdomain.com')
        self.certbot_path = self._find_certbot()

    def _find_certbot(self):
        """Find certbot executable path"""
        # Check common locations
        possible_paths = [
            '/usr/bin/certbot',
            '/usr/local/bin/certbot',
            '/snap/bin/certbot',
        ]

        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path

        # Try using shutil.which
        certbot = shutil.which('certbot')
        if certbot:
            return certbot

        return None

    def provision_certificate(self, test_mode=False):
        """Provision SSL certificate using Certbot"""
        if not self.certbot_path:
            return {
                'success': False,
                'error': 'Certbot not found. Please install certbot.'
            }

        # Check if certificate already exists
        cert_path = f"/etc/letsencrypt/live/{self.domain}/fullchain.pem"
        if os.path.exists(cert_path):
            logger.info(f"Certificate already exists for {self.domain}")
            return {
                'success': True,
                'cert_path': cert_path,
                'key_path': f"/etc/letsencrypt/live/{self.domain}/privkey.pem",
                'message': 'Certificate already exists'
            }

        try:
            # Build Certbot command with full path
            cmd = [
                self.certbot_path, 'certonly', '--nginx',
                '-d', self.domain,
                '--non-interactive',
                '--agree-tos',
                '--email', self.email,
                '--keep-until-expiring'
            ]

            logger.info(f"Running Certbot: {' '.join(cmd)}")

            # Use sudo to run certbot (if needed)
            # Uncomment if running without sudo doesn't work:
            # cmd = ['sudo'] + cmd

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0 and os.path.exists(cert_path):
                return {
                    'success': True,
                    'cert_path': cert_path,
                    'key_path': f"/etc/letsencrypt/live/{self.domain}/privkey.pem",
                    'output': result.stdout
                }
            else:
                logger.error(f"Certbot failed: {result.stderr}")
                return {
                    'success': False,
                    'error': result.stderr or 'Certbot failed',
                    'stdout': result.stdout
                }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'SSL provisioning timed out'
            }
        except Exception as e:
            logger.error(f"SSL provisioning error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def delete_certificate(self):
        """Delete SSL certificate using Certbot."""
        if not any(
            target.exists() or target.is_symlink()
            for target in self._certificate_targets()
        ):
            logger.info(f"Certificate does not exist for {self.domain}")
            return {
                'success': True,
                'message': 'Certificate does not exist'
            }

        if not self.certbot_path:
            logger.warning(f"Certbot not found while deleting certificate for {self.domain}; using file cleanup fallback")
            return self.delete_certificate_files()

        try:
            cmd = [
                self.certbot_path, 'delete',
                '--cert-name', self.domain,
                '--non-interactive',
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                logger.info(f"Certificate deleted for {self.domain}")
                file_result = self.delete_certificate_files()
                if not file_result.get('success'):
                    return file_result
                return {
                    'success': True,
                    'output': result.stdout,
                    'removed': file_result.get('removed', []),
                }
            logger.error(f"Certbot delete failed: {result.stderr}")
            file_result = self.delete_certificate_files()
            if file_result.get('success'):
                return {
                    'success': True,
                    'output': result.stdout,
                    'certbot_error': result.stderr or 'Certbot delete failed',
                    'removed': file_result.get('removed', []),
                }
            return {
                'success': False,
                'error': result.stderr or 'Certbot delete failed',
                'stdout': result.stdout,
                'file_cleanup_error': file_result.get('error'),
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'SSL deletion timed out'
            }
        except Exception as e:
            logger.error(f"SSL deletion error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _certificate_targets(self):
        return [
            LETSENCRYPT_ROOT / 'live' / self.domain,
            LETSENCRYPT_ROOT / 'archive' / self.domain,
            LETSENCRYPT_ROOT / 'renewal' / f'{self.domain}.conf',
        ]

    def delete_certificate_files(self):
        """Remove the Let's Encrypt files Certbot creates for this domain."""
        targets = self._certificate_targets()

        try:
            root = LETSENCRYPT_ROOT.resolve()
            for target in targets:
                try:
                    resolved_parent = target.parent.resolve()
                except FileNotFoundError:
                    resolved_parent = target.parent

                if root not in [resolved_parent, *resolved_parent.parents]:
                    return {
                        'success': False,
                        'error': f'Refusing to remove path outside {LETSENCRYPT_ROOT}: {target}',
                    }

            removed = []
            for target in targets:
                if target.is_dir():
                    shutil.rmtree(target)
                    removed.append(str(target))
                elif target.exists() or target.is_symlink():
                    target.unlink()
                    removed.append(str(target))

            return {
                'success': True,
                'removed': removed,
                'message': 'Certificate files removed',
            }
        except Exception as e:
            logger.error(f"SSL file cleanup error for {self.domain}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
            }

    # services/ssl_provisioning_service.py

    def provision_certificate_webroot(self, webroot_path: str) -> dict:
        """
        Provision SSL certificate using Certbot's webroot plugin.
        webroot_path: absolute path to the domain's root (where index.html lives)
        """
        if not self.certbot_path:
            return {'success': False, 'error': 'Certbot not found'}

        cert_path = f"/etc/letsencrypt/live/{self.domain}/fullchain.pem"
        if os.path.exists(cert_path):
            return {'success': True, 'cert_path': cert_path, 'message': 'Certificate already exists'}

        cmd = [
            self.certbot_path, 'certonly', '--webroot',
            '-w', webroot_path,
            '-d', self.domain,
            '--non-interactive', '--agree-tos',
            '--email', self.email,
            '--keep-until-expiring'
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(cert_path):
                return {'success': True, 'cert_path': cert_path}
            else:
                return {'success': False, 'error': result.stderr or 'Certbot failed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
