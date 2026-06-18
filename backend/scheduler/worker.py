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
from backend.scheduler.jobs.fundamentals_run import run as fundamentals_run
from backend.scheduler.jobs.corporate_actions_run import run as corporate_actions_run
from backend.scheduler.jobs.signal_snapshot_run import run as signal_snapshot_run
from backend.scheduler.jobs.weight_tuning_run import run as weight_tuning_run
from backend.scheduler.jobs.paper_auto_run import run as paper_auto_run
from backend.scheduler.jobs.india_signals_run import run as india_signals_run
from backend.scheduler.jobs.regime_run import run as regime_run
from backend.scheduler.jobs.events_run import run as events_run
from backend.scheduler.jobs.stops_run import run as stops_run
from backend.scheduler.jobs.data_quality_run import run as data_quality_run
from backend.scheduler.jobs.ml_train_run import run as ml_train_run

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(market_run, CronTrigger.from_crontab(settings.market_refresh_cron), id="market_refresh")
    scheduler.add_job(analytics_run, CronTrigger.from_crontab(settings.analytics_refresh_cron), id="analytics_run")
    scheduler.add_job(anomaly_run, CronTrigger.from_crontab(settings.anomaly_scan_cron), id="anomaly_scan")
    scheduler.add_job(doc_run, CronTrigger.from_crontab(settings.doc_refresh_cron), id="doc_refresh")
    scheduler.add_job(report_run, CronTrigger.from_crontab(settings.report_refresh_cron), id="report_run")
    scheduler.add_job(sentiment_run, CronTrigger.from_crontab(settings.sentiment_refresh_cron), id="sentiment_run")
    scheduler.add_job(decision_run, CronTrigger.from_crontab(settings.decision_refresh_cron), id="decision_run")
    scheduler.add_job(fundamentals_run, CronTrigger.from_crontab(settings.fundamentals_refresh_cron), id="fundamentals_run")
    scheduler.add_job(corporate_actions_run, CronTrigger.from_crontab(settings.corporate_actions_cron), id="corporate_actions_run")
    scheduler.add_job(signal_snapshot_run, CronTrigger.from_crontab(settings.signal_snapshot_cron), id="signal_snapshot_run")
    scheduler.add_job(weight_tuning_run, CronTrigger.from_crontab(settings.weight_tuning_cron), id="weight_tuning_run")
    scheduler.add_job(paper_auto_run, CronTrigger.from_crontab(settings.paper_auto_trade_cron), id="paper_auto_run")
    scheduler.add_job(india_signals_run, CronTrigger.from_crontab(settings.india_signals_cron), id="india_signals_run")
    scheduler.add_job(regime_run, CronTrigger.from_crontab(settings.regime_cron), id="regime_run")
    scheduler.add_job(events_run, CronTrigger.from_crontab(settings.events_cron), id="events_run")
    scheduler.add_job(stops_run, CronTrigger.from_crontab(settings.stops_cron), id="stops_run")
    scheduler.add_job(data_quality_run, CronTrigger.from_crontab(settings.data_quality_cron), id="data_quality_run")
    scheduler.add_job(ml_train_run, CronTrigger.from_crontab(settings.ml_train_cron), id="ml_train_run")
    scheduler.start()
