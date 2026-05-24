from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import settings
from backend.scheduler.jobs.market_refresh import run as market_run
from backend.scheduler.jobs.analytics_run import run as analytics_run
from backend.scheduler.jobs.anomaly_scan import run as anomaly_run
from backend.scheduler.jobs.doc_refresh import run as doc_run
from backend.scheduler.jobs.report_run import run as report_run
from backend.scheduler.jobs.sentiment_run import run as sentiment_run
from backend.scheduler.jobs.decision_run import run as decision_run

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(market_run, CronTrigger.from_crontab(settings.market_refresh_cron), id="market_refresh")
    scheduler.add_job(analytics_run, CronTrigger.from_crontab(settings.analytics_refresh_cron), id="analytics_run")
    scheduler.add_job(anomaly_run, CronTrigger.from_crontab(settings.anomaly_scan_cron), id="anomaly_scan")
    scheduler.add_job(doc_run, CronTrigger.from_crontab(settings.doc_refresh_cron), id="doc_refresh")
    scheduler.add_job(report_run, CronTrigger.from_crontab(settings.report_refresh_cron), id="report_run")
    scheduler.add_job(sentiment_run, CronTrigger.from_crontab(settings.sentiment_refresh_cron), id="sentiment_run")
    scheduler.add_job(decision_run, CronTrigger.from_crontab(settings.decision_refresh_cron), id="decision_run")
    scheduler.start()
