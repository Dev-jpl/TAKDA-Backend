from googleapiclient.discovery import build
from .google_auth_service import google_auth_service
from typing import List, Dict, Any, Optional
import base64

class GoogleGmailService:
    def get_recent_emails(self, user_id: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Fetches recent emails from the user's Gmail account."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return []

        service = build('gmail', 'v1', credentials=creds)
        
        # Get list of messages
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        email_details = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            
            # Simple header extraction
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            snippet = msg_data.get('snippet', '')
            
            email_details.append({
                "id": msg['id'],
                "threadId": msg['threadId'],
                "subject": subject,
                "from": sender,
                "date": date,
                "snippet": snippet,
                "link": f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}"
            })
            
        return email_details

google_gmail_service = GoogleGmailService()
