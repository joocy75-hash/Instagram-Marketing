"""
Every 30 Minutes Cron Job - Kill-Switch 모니터링
=================================================
30분마다 실행되어 활성 광고 성과를 체크하고
저성과 광고 중단 / 고성과 광고 예산 증액을 자동 수행

실행: python -m cron.every_30min
또는: python cron/every_30min.py

Crontab 설정 예시:
*/30 * * * * cd /path/to/instagram-marketing && python -m cron.every_30min
"""

import sys
import os
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import get_logger
from utils.slack_notifier import get_notifier
from paid.kill_switch import KillSwitch


# 로거 설정
logger = get_logger("cron.every_30min")


def run_kill_switch_monitoring():
    """
    Kill-Switch 모니터링 실행

    주요 기능:
    1. 활성 광고 성과 체크
    2. 저성과 광고 자동 중단
    3. 고성과 광고 예산 증액
    4. 결과 Slack 알림
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"[Cron] Kill-Switch 모니터링 시작")
    logger.info(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    notifier = get_notifier()

    try:
        # KillSwitch 인스턴스 생성
        kill_switch = KillSwitch()

        # 모든 활성 광고 모니터링 실행
        stats = kill_switch.monitor_all_ads()

        # 결과 로깅
        logger.info("-" * 40)
        logger.info("Kill-Switch 실행 결과:")
        logger.info(f"  - 총 광고 수: {stats['total']}개")
        logger.info(f"  - 유지: {stats['kept']}개")
        logger.info(f"  - 중단됨: {stats['paused']}개")
        logger.info(f"  - 예산 증액: {stats['scaled']}개")
        logger.info(f"  - 에러: {stats['errors']}개")

        # 실행 시간 계산
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 요약 Slack 알림 (변경사항이 있는 경우에만)
        if stats['paused'] > 0 or stats['scaled'] > 0:
            notifier.send(
                message=(
                    f"Kill-Switch 모니터링 완료\n"
                    f"- 총 광고: {stats['total']}개\n"
                    f"- 중단: {stats['paused']}개\n"
                    f"- 증액: {stats['scaled']}개\n"
                    f"- 실행 시간: {duration:.1f}초"
                ),
                title="Kill-Switch 30분 모니터링",
                color="#2196f3" if stats['errors'] == 0 else "#ff9800",
                fields={
                    "총 광고": f"{stats['total']}개",
                    "중단된 광고": f"{stats['paused']}개",
                    "증액된 광고": f"{stats['scaled']}개",
                    "실행 시간": f"{duration:.1f}초",
                }
            )

        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초")
        logger.info("=" * 60)

        return stats

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        error_msg = f"Kill-Switch 모니터링 실패: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)

        # 에러 Slack 알림
        notifier.notify_error(
            error_msg=str(e),
            context="cron.every_30min.run_kill_switch_monitoring"
        )

        logger.info(f"종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"실행 시간: {duration:.1f}초 (실패)")
        logger.info("=" * 60)

        raise


def main():
    """메인 진입점"""
    try:
        stats = run_kill_switch_monitoring()

        # 정상 종료
        sys.exit(0)

    except Exception as e:
        logger.error(f"Cron 작업 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
