"""Train station constants"""

from dataclasses import dataclass


@dataclass
class StationInfo:
    name: str
    code: str


# KTX 역 정보
KTX_STATIONS = [
    StationInfo("서울", "NAT010000"),
    StationInfo("용산", "NAT010415"),
    StationInfo("광명", "NAT010754"),
    StationInfo("천안아산", "NAT011668"),
    StationInfo("오송", "NAT011072"),
    StationInfo("대전", "NAT011426"),
    StationInfo("김천구미", "NAT012055"),
    StationInfo("동대구", "NAT013271"),
    StationInfo("경주", "NAT013502"),
    StationInfo("울산", "NAT013707"),
    StationInfo("부산", "NAT014445"),
    StationInfo("공주", "NAT011895"),
    StationInfo("익산", "NAT012296"),
    StationInfo("정읍", "NAT012355"),
    StationInfo("광주송정", "NAT012425"),
    StationInfo("목포", "NAT012489"),
]