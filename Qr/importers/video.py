from .base import BaseQRImporter
from ..models import QRCode, QRCodeData


class VideoImporter(BaseQRImporter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    required_columns = [
        "QrName",
        "page_title",
    ]

    def process_row(self, row, job, row_number):
        qr_name = row.get("QrName")
        wifi_name = row.get("WifiName")
        password = row.get("password")

        if not qr_name:
            raise ValueError("QrName is required.")

        if not wifi_name:
            raise ValueError("WifiName is required.")

        if password is None or password == "":
            raise ValueError("password is required.")

        qr_type = job.qr_type

        qr= QRCode.objects.create(name=qr_name, qr_type=qr_type,created_by=job.user)
        QRCodeData.objects.create(qr_code=qr,
                                  content_json= {
                        "open_mode": "landing-page-with-player",
                        "page_title": "Product Demonstration Videos",
                        "playlist_id": "playlist-123",
                        "items": [
                            {
                            "id": "video-1",
                            "input_type": "video-url",
                            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                            "order_no": 1,
                            "title": "Introduction Video",
                            "description": "Overview of key features and setup instructions.",
                            "thumbnail": "/media/thumb1.jpg",
                            "duration": 180,
                            "playlist_id": "playlist-123"
                            },
                            {
                            "id": "video-2",
                            "input_type": "general-upload",
                            "url": "",
                            "video_url": "/media/uploads/demo.mp4",
                            "order_no": 2,
                            "title": "Uploaded Demo",
                            "description": "High resolution MP4 walkthrough.",
                            "thumbnail": "/media/thumb2.jpg",
                            "video_id": "media-456",
                            "playlist_id": "playlist-123"
                            }
                        ],
                        "page_style": {
                            "theme": "video-1",
                            "color": "#009DE2",
                            "corner_style": "sharp"
                        }
                        })