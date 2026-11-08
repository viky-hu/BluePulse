from datetime import date

from fastapi import Depends
from sqlalchemy.orm import Session

from .daily_reports import daily_index, daily_navigation, daily_window, load_daily
from .hotspots import load_hot
from .models import now_utc


def register_editions(router, session_dep, ApiError) -> None:
    def check_key(key: str) -> None:
        try:
            daily_window(key)
        except (ValueError, OverflowError):
            raise ApiError(404, "daily_not_found", "没有找到这一期日报。") from None

    @router.get("/site/hot")
    def hot(session: Session = Depends(session_dep)):
        return load_hot(session)

    @router.get("/site/reports/daily/latest-page")
    def latest(session: Session = Depends(session_dep)):
        now = now_utc()
        index = daily_index(session, now)
        if not index:
            return {"index": [], "report": None}
        key = index[0]["key"]
        return {"index": daily_navigation(index, key), "report": load_daily(session, key, now)}

    @router.get("/site/reports/daily")
    def index(session: Session = Depends(session_dep)):
        return {"kind": "daily", "items": daily_index(session)}

    @router.get("/site/reports/daily/navigation/{key}")
    def navigation(key: str, session: Session = Depends(session_dep)):
        check_key(key)
        return {"items": daily_navigation(daily_index(session), key)}

    @router.get("/site/reports/daily/months/{month}")
    def month_index(month: str, session: Session = Depends(session_dep)):
        try:
            if date.fromisoformat(f"{month}-01").isoformat()[:7] != month:
                raise ValueError
        except ValueError:
            raise ApiError(404, "daily_month_not_found", "没有找到这个日报月份。") from None
        return {"items": [{"key": row["key"], "issueNumber": row["issueNumber"], "title": row["title"]}
                          for row in daily_index(session) if row["key"][:7] == month]}

    @router.get("/site/reports/daily/{key}")
    def detail(key: str, session: Session = Depends(session_dep)):
        check_key(key)
        report = load_daily(session, key)
        if report is None:
            raise ApiError(404, "daily_not_found", "没有找到这一期日报。")
        return report
