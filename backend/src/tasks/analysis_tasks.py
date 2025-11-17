"""Analysis tasks for Celery"""
from celery import Task
from datetime import datetime
import logging
from typing import Optional

from .celery_app import celery_app
from src.database import SessionLocal, Wallet, AnalysisRequest
from src.ml.visualizer import WalletBehaviorAnalyzer

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task with database session handling"""
    _db = None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True, name='analyze_wallet_task')
def analyze_wallet_task(self, request_id: str):
    """
    Analyze a wallet address (on-demand request)

    Steps:
    1. Fetch all transactions for target address
    2. Extract connected wallets
    3. Fetch connected wallets up to graph_depth
    4. Classify tokens and calculate metrics
    5. Run ML analysis
    6. Update database
    7. Send notification email
    """
    db = self.db

    try:
        # Get request
        request = db.query(AnalysisRequest).filter_by(request_id=request_id).first()
        if not request:
            logger.error(f"Request {request_id} not found")
            return {'status': 'error', 'message': 'Request not found'}

        # Update status
        request.status = 'processing'
        request.started_at = datetime.utcnow()
        db.commit()

        logger.info(f"Starting analysis for {request.wallet_address} (request: {request_id})")

        # TODO: Implement full analysis pipeline
        # For now, just mark as completed
        # In production, this will:
        # 1. Call collectors to fetch data
        # 2. Process and store in database
        # 3. Run ML analysis
        # 4. Update wallet records
        # 5. Send email notification

        # Placeholder implementation
        request.status = 'completed'
        request.completed_at = datetime.utcnow()
        request.result_url = f"/api/v2/analysis/results/{request_id}"
        db.commit()

        logger.info(f"Analysis completed for {request_id}")

        # TODO: Send email notification
        # if settings.email_notifications_enabled:
        #     send_completion_email(request.user_email, request_id)

        return {
            'status': 'completed',
            'request_id': request_id,
            'wallet_address': request.wallet_address
        }

    except Exception as e:
        logger.error(f"Error analyzing wallet {request_id}: {e}")

        # Update request status
        request = db.query(AnalysisRequest).filter_by(request_id=request_id).first()
        if request:
            request.status = 'failed'
            request.error_message = str(e)
            db.commit()

        raise


@celery_app.task(base=DatabaseTask, bind=True, name='refresh_wallet_task')
def refresh_wallet_task(self, wallet_address: str):
    """
    Refresh data for an existing wallet

    Lighter than full analysis - only updates recent transactions
    """
    db = self.db

    try:
        logger.info(f"Refreshing wallet {wallet_address}")

        wallet = db.query(Wallet).filter_by(address=wallet_address).first()
        if not wallet:
            logger.warning(f"Wallet {wallet_address} not found for refresh")
            return {'status': 'error', 'message': 'Wallet not found'}

        # TODO: Implement refresh logic
        # 1. Fetch new transactions since last_updated
        # 2. Update metrics
        # 3. Re-run classification if significant changes

        wallet.last_updated = datetime.utcnow()
        db.commit()

        logger.info(f"Wallet {wallet_address} refreshed")

        return {
            'status': 'completed',
            'wallet_address': wallet_address
        }

    except Exception as e:
        logger.error(f"Error refreshing wallet {wallet_address}: {e}")
        raise


@celery_app.task(name='send_notification_email')
def send_notification_email(email: str, request_id: str, status: str = 'completed'):
    """Send email notification when analysis is complete"""
    try:
        # TODO: Implement with SendGrid
        logger.info(f"Sending notification email to {email} for request {request_id}")

        # Placeholder
        # from sendgrid import SendGridAPIClient
        # from sendgrid.helpers.mail import Mail
        #
        # message = Mail(
        #     from_email=settings.notification_email_from,
        #     to_emails=email,
        #     subject=f"Your wallet analysis is {status}",
        #     html_content=f"..."
        # )
        #
        # sg = SendGridAPIClient(settings.sendgrid_api_key)
        # response = sg.send(message)

        return {'status': 'sent', 'email': email}

    except Exception as e:
        logger.error(f"Error sending email to {email}: {e}")
        raise
