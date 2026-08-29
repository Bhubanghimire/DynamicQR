# services/ssl_provisioning_service.py

import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)


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