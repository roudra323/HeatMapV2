"""Scheduled tasks for periodic jobs"""
import logging
from datetime import datetime, timedelta
from .celery_app import celery_app
from src.database import SessionLocal, Wallet
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name='scheduled_refresh_task')
def scheduled_refresh_task():
    """
    Weekly scheduled task to refresh all stale wallet data

    Runs every Sunday at 2 AM
    """
    db = SessionLocal()

    try:
        logger.info("Starting scheduled wallet refresh")

        # Get refresh interval from config
        refresh_days = 7  # Default, can be loaded from SystemConfig

        # Find stale wallets
        cutoff_date = datetime.utcnow() - timedelta(days=refresh_days)
        stale_wallets = db.query(Wallet).filter(
            Wallet.last_updated < cutoff_date,
            Wallet.analysis_status == 'completed'
        ).all()

        logger.info(f"Found {len(stale_wallets)} stale wallets to refresh")

        # Queue refresh tasks
        from .analysis_tasks import refresh_wallet_task

        refreshed = 0
        for wallet in stale_wallets:
            try:
                refresh_wallet_task.delay(wallet.address)
                refreshed += 1

                # Batch commit every 100 wallets
                if refreshed % 100 == 0:
                    logger.info(f"Queued {refreshed} refresh tasks...")

            except Exception as e:
                logger.error(f"Error queuing refresh for {wallet.address}: {e}")

        logger.info(f"✅ Scheduled refresh completed. Queued {refreshed} wallets")

        return {
            'status': 'completed',
            'wallets_queued': refreshed,
            'total_stale': len(stale_wallets)
        }

    except Exception as e:
        logger.error(f"Error in scheduled refresh: {e}")
        raise

    finally:
        db.close()
