"""SONIC AI — Live Automation Platform.

This package turns the system from a passive library into a **live
automation platform** that runs jobs in the background, watches the
filesystem, schedules recurring tasks, and exposes a real-time web
dashboard.

Public surface (stable, opt-in):
    - ``realtime_engine`` — in-memory job queue with progress tracking
    - ``workflow_templates`` — pre-built automation recipes
    - ``proactive_monitor`` — file watcher + scheduled task executor
    - ``dashboard``        — Flask-based live web dashboard
"""
