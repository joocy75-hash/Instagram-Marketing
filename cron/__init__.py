# Cron Jobs Module
# 스케줄 작업 (모니터링, 리포트 등)
#
# 사용 가능한 Cron 작업:
# - every_30min: Kill-Switch 모니터링 (30분마다)
# - hourly: 댓글 폴링 체크 (매시간)
# - daily: 일일 성과 리포트 (매일 오전 9시)
#
# 실행 방법:
#   python -m cron.every_30min
#   python -m cron.hourly
#   python -m cron.daily
#
# Crontab 설정 예시:
#   */30 * * * * cd /path/to/instagram-marketing && python -m cron.every_30min
#   0 * * * * cd /path/to/instagram-marketing && python -m cron.hourly
#   0 9 * * * cd /path/to/instagram-marketing && python -m cron.daily

__all__ = [
    "every_30min",
    "hourly",
    "daily",
]
