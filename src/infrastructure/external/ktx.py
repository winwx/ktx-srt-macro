# -*- coding: utf-8 -*-
"""
    korail2.korail2
    ~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Taehoon Kim.
    :license: BSD, see LICENSE for more details.

    Dynapath 우회 패치는 ukkidokiyo/korail2 fork(2026-08-01 기준)에서
    가져와 이 프로젝트에 vendored 형태로 포함함. 코레일 앱의
    Dynapath anti-bot 체크(x-dynapath-m-token / Sid / 최신 app version)를
    통과하기 위한 로직으로, 순수 로컬 인코딩 알고리즘이며 외부 네트워크
    호출은 없음.
"""
import re
import requests
import itertools
import sys
import base64
import time
import random
import string
import hashlib

from datetime import datetime, timedelta
from six import with_metaclass
from pprint import pprint
from datetime import timezone
from Crypto.Util.Padding import pad
from Crypto.Cipher import AES

try:
    # noinspection PyPackageRequirements
    import simplejson as json
except ImportError:
    import json


def _python3():
    return sys.version_info > (3, 0)

if _python3():
    from functools import reduce

EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")
PHONE_NUMBER_REGEX = re.compile(r"(\d{3})-(\d{3,4})-(\d{4})")

SCHEME = "https"
KORAIL_HOST = "smart.letskorail.com"
KORAIL_PORT = "443"

KORAIL_DOMAIN = "%s://%s:%s" % (SCHEME, KORAIL_HOST, KORAIL_PORT)
KORAIL_MOBILE = "%s/classes/com.korail.mobile" % KORAIL_DOMAIN

KORAIL_LOGIN = "%s.login.Login" % KORAIL_MOBILE
KORAIL_LOGOUT = "%s.common.logout" % KORAIL_MOBILE
KORAIL_SEARCH_SCHEDULE = "%s.seatMovie.ScheduleView" % KORAIL_MOBILE
KORAIL_TICKETRESERVATION = "%s.certification.TicketReservation" % KORAIL_MOBILE
KORAIL_RESERVATION_PAYMENT = "%s.payment.ReservationPayment" % KORAIL_MOBILE
KORAIL_RESERVATION_INQUIRY = "%s.certification.ReservationList" % KORAIL_MOBILE
KORAIL_REFUND = "%s.refunds.RefundsRequest" % KORAIL_MOBILE
KORAIL_MYTICKETLIST = "%s.myTicket.MyTicketList" % KORAIL_MOBILE
KORAIL_MYTICKET_SEAT = "%s.refunds.SelTicketInfo" % KORAIL_MOBILE

KORAIL_MYRESERVATIONLIST = "%s.reservation.ReservationView" % KORAIL_MOBILE
KORAIL_CANCEL = "%s.reservationCancel.ReservationCancelChk" % KORAIL_MOBILE

KORAIL_STATION_DB = "%s.common.stationinfo?device=ip" % KORAIL_MOBILE
KORAIL_STATION_DB_DATA = "%s.common.stationdata" % KORAIL_MOBILE
KORAIL_EVENT = "%s.common.event" % KORAIL_MOBILE
KORAIL_PAYMENT = "%s/ebizmw/PrdPkgMainList.do" % KORAIL_DOMAIN
KORAIL_PAYMENT_VOUCHER = "%s/ebizmw/PrdPkgBoucherView.do" % KORAIL_DOMAIN

KORAIL_CODE = "%s.common.code.do" % KORAIL_MOBILE
KORAIL_NCARD_SCHEDULE_VIEW = "%s.research.dcntCrdScheduleView.do" % KORAIL_MOBILE
KORAIL_NCARD_USE_HISTORY = "%s.ticket.dcntCrdUseQry.do" % KORAIL_MOBILE
KORAIL_SEAT_ASSIGN_SCHEDULE_VIEW = "%s.research.assignScheduleView.do" % KORAIL_MOBILE

KORAIL_TICKET_CHANGE_DATES = "%s.reservation.tripChgDate.do" % KORAIL_MOBILE
KORAIL_TICKET_CHANGE_ORIGINAL = "%s.research.tripChgOgtk.do" % KORAIL_MOBILE
KORAIL_TICKET_CHANGE_RESERVATION = "%s.reservation.tripChgPrsC.do" % KORAIL_MOBILE
KORAIL_TICKET_CHANGE_SETTLEMENT = "%s.pay.intgStl.do" % KORAIL_MOBILE
KORAIL_TICKET_CHANGE_ROLLBACK = "%s.ticket.tripChgHndgCnc.do" % KORAIL_MOBILE

NCARD_DISCOUNT_CODE = "153"
NCARD_SEAT_ASSIGN_MENU_ID = "A2"

DEFAULT_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; SM-S928N Build/UP1A.231005.007)"

# requests 기본값은 타임아웃이 없어서, 서버가 응답을 안 주면 호출 스레드가
# 영원히 멈춘다(예: 로그인 버튼이 다시 활성화되지 않는 버그로 이어짐).
REQUEST_TIMEOUT = 15

DYNAPATH_PATHS = [
    "/classes/com.korail.mobile.certification.TicketReservation",
    "/classes/com.korail.mobile.nonMember.NonMemTicket",
    "/classes/com.korail.mobile.seatMovie.ScheduleView",
    "/classes/com.korail.mobile.seatMovie.ScheduleViewSpecial",
    "/classes/com.korail.mobile.trn.prcFare.do",
    "/classes/com.korail.mobile.login.Login"
]

class DynaPathMasterEngine:
    APP_ID = "com.korail.talk"
    AS_VALUE = "%5B38ff229cb34c7dda8e28220a2d750cce%5D"
    DEVICE_MODEL = "SM-S928N"
    OS_TYPE = "Android"
    SDK_VERSION = "v1"

    def __init__(self):
        self.TABLE = "3FE9jgRD4KdCyuawklqGJYmvfMn15P7US8XbxeLQtWT6OicBAopINs2Vh0HZrz"
        self.I8, self.I9, self.I10 = 161, 30, 2
        self.app_start_ts = str(int(time.time() * 1000))

    def string2xA1s(self, data_str):
        result = []
        i = 0
        while i < len(data_str):
            cp = ord(data_str[i])
            i += 1
            if cp < 128: result.append(cp)
            elif cp < 2048:
                result.append(128 | ((cp >> 7) & 15))
                result.append(cp & 127)
            elif cp >= 262144:
                result.append(160)
                result.append((cp >> 14) & 127)
                result.append((cp >> 7) & 127)
                result.append(cp & 127)
            elif (63488 & cp) != 55296:
                result.append(((cp >> 14) & 15) | 144)
                result.append((cp >> 7) & 127)
                result.append(cp & 127)
        return result

    def make_key(self, key_str):
        big_int_add = 0
        for char in key_str:
            cp = ord(char)
            i9_bit = 32768
            for _ in range(16):
                if (i9_bit & cp) != 0: break
                i9_bit >>= 1
            big_int_add = (big_int_add * (i9_bit << 1)) + cp
        return big_int_add

    def _internal_i(self, base_table, remainder, encode_size, current_sb):
        j8_count = 0
        for k in range(len(base_table)):
            char = base_table[k]
            if char not in current_sb:
                if j8_count == remainder: return char
                j8_count += 1
        return ' '

    def make_encode_table(self, num, encode_size, base_table):
        sb = ""
        temp_num = num
        for i in range(encode_size):
            j8_divisor = encode_size - i
            remainder = temp_num % j8_divisor
            char = self._internal_i(base_table, remainder, len(base_table), sb)
            sb += char
            temp_num //= j8_divisor
        return sb

    def encode_normal_be(self, data_str, table, i8=161, i9=30, i10=2):
        list_data = self.string2xA1s(data_str)
        sb, i_arr = [], [0] * (i10 + 1)
        idx, size = 0, len(list_data) % i10
        size2 = len(list_data) - size
        while idx < size2:
            val = 0
            for _ in range(i10):
                val = (val * i8) + list_data[idx]
                idx += 1
            for i in range(i10 + 1):
                i_arr[i] = val % i9
                val //= i9
            for i in range(i10, -1, -1): sb.append(table[i_arr[i]])
        if size > 0:
            val = 0
            for _ in range(size):
                val = (val * i8) + list_data[idx]
                idx += 1
            for i in range(size + 1):
                i_arr[i] = val % i9
                val //= i9
            while size >= 0:
                sb.append(table[i_arr[size]])
                size -= 1
        return "".join(sb)

    def generate_token(self, device_id, ts, rand):
        plaintext = (f"ai={self.APP_ID}&di={device_id}&as={self.AS_VALUE}&"
                     f"su=false&dbg=false&emu=false&hk=false&it={self.app_start_ts}&"
                     f"ts={ts}&rt=0&os=13&dm={self.DEVICE_MODEL}&st={self.OS_TYPE}&sv={self.SDK_VERSION}")

        dyn_key = f"v1+{rand}+{ts}"
        key_enc = self.encode_normal_be(dyn_key, self.TABLE, self.I8, self.I9, self.I10)
        big_key = self.make_key(dyn_key)
        custom_table = self.make_encode_table(big_key, self.I9, self.TABLE)
        body_enc = self.encode_normal_be(plaintext, custom_table, self.I8, self.I9, self.I10)
        return f"bEeEP{self.TABLE[len(key_enc)]}{key_enc}{body_enc}"

def _get_utf8(data, key, default=None):
    v = data.get(key, default)

    if _python3():
        return v

    if isinstance(v, basestring):
        return v.encode('utf-8')
    else:
        return v


def _get_first(data, keys, default=None):
    for key in keys:
        value = _get_utf8(data, key)
        if value is not None:
            return value
    return default


def _require_nonempty_str(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a nonempty string" % field)
    return value


class Schedule(object):
    """Korail train object. Highly inspired by `korail.py
    <https://raw.githubusercontent.com/devxoul/korail/master/korail/korail.py>`_
    by `Suyeol Jeon <http://xoul.kr/>`_ at 2014.
    """

    # : 기차 종류
    # : 00: KTX
    #: 01: 새마을호
    #: 02: 무궁화호
    #: 03: 통근열차
    #: 04: 누리로
    #: 05: 전체 (검색시에만 사용)
    #: 06: 공학직통
    #: 07: KTX-산천
    #: 08: ITX-새마을
    #: 09: ITX-청춘
    train_type = None  # h_trn_clsf_cd, selGoTrain

    train_group = None # h_trn_gp_cd

    #: 기차 종류 이름
    train_type_name = None  # h_trn_clsf_nm

    #: 기차 번호
    train_no = None  # h_trn_no

    #: 출발역 이름
    dep_name = None  # h_dpt_rs_stn_nm

    #: 출발역 코드
    dep_code = None  # h_dpt_rs_stn_cd

    #: 출발 날짜 (yyyyMMdd)
    dep_date = None  # h_dpt_dt

    #: 출발 시각 (hhmmss)
    dep_time = None  # h_dpt_tm

    #: 도착역 이름
    arr_name = None  # h_arv_rs_stn_nm

    #: 도착역 코드
    arr_code = None  # h_arv_rs_stn_cd

    #: 도착 날짜 (yyyyMMdd)
    arr_date = None  # h_arv_dt

    #: 도착 시각 (hhmmss)
    arr_time = None  # h_arv_tm

    #: 운행 날짜 (yyyyMMdd)
    run_date = None  # h_run_dt


    def __init__(self, data):

        self.raw = data

        self.train_type = _get_utf8(data, 'h_trn_clsf_cd')
        self.train_type_name = _get_utf8(data, 'h_trn_clsf_nm')
        self.train_group = _get_utf8(data, 'h_trn_gp_cd')
        self.train_no = _get_utf8(data, 'h_trn_no')
        self.delay_time = _get_utf8(data, 'h_expct_dlay_hr')

        self.dep_name = _get_utf8(data, 'h_dpt_rs_stn_nm')
        self.dep_code = _get_utf8(data, 'h_dpt_rs_stn_cd')
        self.dep_date = _get_utf8(data, 'h_dpt_dt')
        self.dep_time = _get_utf8(data, 'h_dpt_tm')

        self.arr_name = _get_utf8(data, 'h_arv_rs_stn_nm')
        self.arr_code = _get_utf8(data, 'h_arv_rs_stn_cd')
        self.arr_date = _get_utf8(data, 'h_arv_dt')
        self.arr_time = _get_utf8(data, 'h_arv_tm')

        self.run_date = _get_utf8(data, 'h_run_dt')
        self.dep_station_cons_order = _get_first(
            data, ('h_dpt_stn_cons_ordr', 'dptStnConsOrdr'))
        self.dep_station_run_order = _get_first(
            data, ('h_dpt_stn_run_ordr', 'dptStnRunOrdr'))
        self.arr_station_cons_order = _get_first(
            data, ('h_arv_stn_cons_ordr', 'arvStnConsOrdr'))
        self.arr_station_run_order = _get_first(
            data, ('h_arv_stn_run_ordr', 'arvStnRunOrdr'))

    def __repr__(self):
        dep_time = "%s:%s" % (self.dep_time[:2], self.dep_time[2:4])
        arr_time = "%s:%s" % (self.arr_time[:2], self.arr_time[2:4])

        dep_date = "%s월 %s일" % (int(self.dep_date[4:6]), int(self.dep_date[6:]))

        repr_str = '[%s] %s, %s~%s(%s~%s)' % (
            self.train_type_name,
            dep_date,
            self.dep_name,
            self.arr_name,
            dep_time,
            arr_time,
        )

        return repr_str


class Train(Schedule):
    # : 지연 시간 (hhmm)
    delay_time = None  # h_expct_dlay_hr

    # : 예약 가능 여부
    reserve_possible = False  # h_rsv_psb_flg ('Y' or 'N')

    #: 예약 가능 여부
    reserve_possible_name = None  # h_rsv_psb_nm

    #: 특실 예약가능 여부
    #: 00: 특실 없음
    #: 11: 예약 가능
    #: 13: 매진
    special_seat = None  # h_spe_rsv_cd

    #: 일반실 예약가능 여부
    #: 00: 일반실 없음
    #: 11: 예약 가능
    #: 13: 매진
    general_seat = None  # h_gen_rsv_cd

    #: 예약 대기 가능 여부
    #: -2: 좌석 있음
    #: 9: 예약 대기 (일반석)
    #: 0: 예약 대기 없음 (매진)
    ## 특실의 경우 케이스 예약대기도 09를 사용하는지 확인이 필요함
    wait_reserve_flag = None # h_wait_rsv_flg

    def __init__(self, data):
        super(Train, self).__init__(data)
        self.reserve_possible = _get_utf8(data, 'h_rsv_psb_flg')
        self.reserve_possible_name = _get_utf8(data, 'h_rsv_psb_nm')

        self.special_seat = _get_utf8(data, 'h_spe_rsv_cd')
        self.general_seat = _get_utf8(data, 'h_gen_rsv_cd')
        self.free_seat = _get_utf8(data, 'h_free_rsv_cd')
        self.standing_seat = _get_utf8(data, 'h_stnd_rsv_cd')

        self.wait_reserve_flag = _get_utf8(data, 'h_wait_rsv_flg')
        if self.wait_reserve_flag:
            self.wait_reserve_flag = int(self.wait_reserve_flag)


    def __repr__(self):
        repr_str = super(Train, self).__repr__()

        if self.reserve_possible_name is not None:
            seats = []
            if self.has_special_seat():
                seats.append("특실")

            if self.has_general_seat():
                seats.append("일반실")

            if self.has_general_waiting_list():
                seats.append("예약 대기(일반)")

            repr_str += " " + (",".join(seats)) + " " + self.reserve_possible_name.replace('\n', ' ')

        return repr_str

    def has_special_seat(self):
        return self.special_seat == '11'

    def has_general_seat(self):
        return self.general_seat == '11'

    def has_seat(self):
        return self.has_general_seat() or self.has_special_seat()

    def has_waiting_list(self):
        return self.has_general_waiting_list()

    def has_general_waiting_list(self):
        return self.wait_reserve_flag == 9


class NCardTrain(Train):
    """N-card discounted ticket train candidate returned by KorailTalk."""

    def __init__(self, data):
        self.train_type = _get_first(data, ('h_trn_clsf_cd', 'trnClsfCd', 'trnGpCd'))
        self.train_type_name = _get_first(data, ('h_trn_clsf_nm', 'trnClsfNm', 'dturNm'))
        self.train_group = _get_first(data, ('h_trn_gp_cd', 'trnGpCd'))
        self.train_no = _get_first(data, ('h_trn_no', 'trnNo'))
        self.delay_time = _get_first(data, ('h_expct_dlay_hr', 'expctDlayHr'), '')

        self.dep_name = _get_first(data, ('h_dpt_rs_stn_nm', 'dptRsStnNm'))
        self.dep_code = _get_first(data, ('h_dpt_rs_stn_cd', 'dptRsStnCd'))
        self.dep_date = _get_first(data, ('h_dpt_dt', 'dptDt', 'runDt'))
        self.dep_time = _get_first(data, ('h_dpt_tm', 'dptTm'))

        self.arr_name = _get_first(data, ('h_arv_rs_stn_nm', 'arvRsStnNm'))
        self.arr_code = _get_first(data, ('h_arv_rs_stn_cd', 'arvRsStnCd'))
        self.arr_date = _get_first(data, ('h_arv_dt', 'arvDt', 'runDt'))
        self.arr_time = _get_first(data, ('h_arv_tm', 'arvTm'))

        self.run_date = _get_first(data, ('h_run_dt', 'runDt', 'dptDt'))
        self.dep_station_cons_order = _get_first(
            data, ('h_dpt_stn_cons_ordr', 'dptStnConsOrdr'))
        self.dep_station_run_order = _get_first(
            data, ('h_dpt_stn_run_ordr', 'dptStnRunOrdr'))
        self.arr_station_cons_order = _get_first(
            data, ('h_arv_stn_cons_ordr', 'arvStnConsOrdr'))
        self.arr_station_run_order = _get_first(
            data, ('h_arv_stn_run_ordr', 'arvStnRunOrdr'))
        self.reserve_possible = _get_first(data, ('h_rsv_psb_flg', 'rsvPsbFlg'), 'Y')
        self.reserve_possible_name = _get_first(data, ('h_rsv_psb_nm', 'rsvPsbNm'), '')
        self.special_seat = _get_first(data, ('h_spe_rsv_cd', 'speRsvCd'), '00')
        self.general_seat = _get_first(data, ('h_gen_rsv_cd', 'genRsvCd'), '00')
        self.wait_reserve_flag = _get_first(data, ('h_wait_rsv_flg', 'waitRsvFlg'))
        if self.wait_reserve_flag:
            self.wait_reserve_flag = int(self.wait_reserve_flag)

        self.price = _get_first(data, ('cmtrPrc', 'h_rcvd_amt'))
        self.fare = _get_first(data, ('h_rcvd_fare', 'rcvdFare'))
        self.discount_name = self.reserve_possible_name
        self.general_discount_rate = _get_first(data, ('h_gen_disc_rt', 'genDiscRt'))
        self.special_discount_rate = _get_first(data, ('h_spe_disc_rt', 'speDiscRt'))
        self.train_discount_rate = _get_first(data, ('h_train_disc_gen_rt', 'trainDiscGenRt'))
        self.general_remaining_seats = _get_first(data, ('h_std_rest_seat_cnt', 'stdRestSeatCnt'))
        self.standing_remaining_seats = _get_first(data, ('h_stnd_rest_seat_cnt', 'stndRestSeatCnt'))
        self.standing_seat = _get_first(data, ('h_stnd_rsv_cd', 'stndRsvCd'))
        self.standing_seat_name = _get_first(data, ('h_stnd_rsv_nm', 'stndRsvNm'))
        self.free_remaining_seats = _get_first(data, ('h_free_rest_seat_cnt', 'freeRestSeatCnt'))
        self.free_seat = _get_first(data, ('h_free_rsv_cd', 'freeRsvCd'))
        self.free_seat_name = _get_first(data, ('h_free_rsv_nm', 'freeRsvNm'))
        self.seat_attribute = _get_first(
            data,
            ('h_seat_att_cd', 'h_seat_att_cd1', 'seatAttCd', 'seatAttCd1'),
        )
        self.route_code = _get_first(data, ('routCd', 'h_rout_cd'))
        self.route_name = _get_first(data, ('dturNm', 'h_rout_nm'))
        self.raw = data

    def has_free_seat(self):
        if self.standing_seat == '11':
            return True
        return self.free_seat == '11'

    def has_ncard_general_seat(self, include_auxiliary=False):
        return self.general_seat in ('11', '21') or (
            include_auxiliary and
            self.general_seat == '13' and
            self.has_free_seat()
        )

    def has_ncard_special_seat(self):
        return self.special_seat in ('11', '21')

    def __repr__(self):
        train_name = self.train_type_name or self.train_group or "NCard"
        route = "%s~%s" % (self.dep_name or "", self.arr_name or "")
        if self.dep_time and self.arr_time:
            route += "(%s:%s~%s:%s)" % (
                self.dep_time[:2], self.dep_time[2:4],
                self.arr_time[:2], self.arr_time[2:4],
            )
        if self.price:
            route += " %s원" % self.price
        if self.discount_name:
            route += " %s" % self.discount_name
        return "[%s] %s" % (train_name, route)


class NCard:
    """Owned N-card metadata from KorailTalk's MyTicket flow."""

    def __init__(self, ticket_data, detail_data=None):
        detail_data = detail_data or {}
        dcnt_info = detail_data.get('dcnt_crd_info') or {}
        segments = dcnt_info.get('appSegList') or dcnt_info.get('appSeg_info') or []

        self.raw_ticket = ticket_data
        self.raw_detail = detail_data
        self.ticket_kind_code = _get_utf8(ticket_data, 'h_tk_knd_cd')
        self.ticket_kind_name = _get_utf8(detail_data, 'h_tk_knd_nm') or _get_utf8(ticket_data, 'h_tk_knd_nm')
        self.valid = _get_utf8(ticket_data, 'cmtrVlidFlg')
        self.dep_name = _get_utf8(ticket_data, 'h_dpt_rs_stn_nm')
        self.arr_name = _get_utf8(ticket_data, 'h_arv_rs_stn_nm')
        self.sale_date = _get_utf8(ticket_data, 'h_orgtk_sale_dt')
        self.sale_info1 = _get_utf8(ticket_data, 'h_orgtk_wct_no')
        self.sale_info2 = _get_utf8(ticket_data, 'h_orgtk_ret_sale_dt')
        self.sale_info3 = _get_utf8(ticket_data, 'h_orgtk_sale_sqno')
        self.sale_info4 = _get_utf8(ticket_data, 'h_orgtk_ret_pwd')
        self.price = _get_utf8(ticket_data, 'h_rcvd_amt')
        self.pnr_no = _get_utf8(ticket_data, 'h_pnr_no')
        self.discount_card_no = _get_utf8(dcnt_info, 'h_dcnt_crd_no')
        self.term_extension_possible = _get_utf8(dcnt_info, 'h_dcnt_crd_trm_extn_psb_flg')
        self.reservation_discount_card_no = _get_utf8(detail_data, 'h_rsv_disc_crd_no')
        self.reservation_discount_card_name = _get_utf8(detail_data, 'h_rsv_disc_crd_knd_nm')
        self.segments = segments

    def get_ticket_no(self):
        return "-".join(map(str, (self.sale_info1, self.sale_info2, self.sale_info3, self.sale_info4)))

    @property
    def dcnt_card_no(self):
        return self.discount_card_no

    def __repr__(self):
        route = "%s~%s" % (self.dep_name or "", self.arr_name or "")
        kind = self.ticket_kind_name or "NCard"
        return "[%s] %s" % (kind, route)


class Ticket(Train):
    """Ticket object"""

    # : 열차 번호
    car_no = None  # h_srcar_no

    # : 자리 갯수
    seat_no_count = None  # h_seat_cnt  ex) 001

    #: 자리 번호
    seat_no = None  # h_seat_no

    #: 자리 번호
    seat_no_end = None  # h_seat_no_end

    #: 구매자 성함
    buyer_name = None  # h_buy_ps_nm

    #: 구매 날짜 (yyyyMMdd)
    sale_date = None  # h_orgtk_sale_dt

    #: 구매 정보1
    sale_info1 = None  # h_orgtk_wct_no

    #: 구매 정보2
    sale_info2 = None  # h_orgtk_ret_sale_dt

    #: 구매 정보3
    sale_info3 = None  # h_orgtk_sale_sqno

    #: 구매 정보4
    sale_info4 = None  # h_orgtk_ret_pwd

    #: 구매 가격
    price = None  # h_rcvd_amt  ex) 00013900

    def __init__(self, data):
        raw_data = data['ticket_list'][0]['train_info'][0]
        super(Ticket, self).__init__(raw_data)

        self.seat_no_end = _get_utf8(raw_data, 'h_seat_no_end')
        self.seat_no_count = int(_get_utf8(raw_data, 'h_seat_cnt'))

        self.buyer_name = _get_utf8(raw_data, 'h_buy_ps_nm')
        self.sale_date = _get_utf8(raw_data, 'h_orgtk_sale_dt')
        self.sale_info1 = _get_utf8(raw_data, 'h_orgtk_wct_no')
        self.sale_info2 = _get_utf8(raw_data, 'h_orgtk_ret_sale_dt')
        self.sale_info3 = _get_utf8(raw_data, 'h_orgtk_sale_sqno')
        self.sale_info4 = _get_utf8(raw_data, 'h_orgtk_ret_pwd')
        self.price = int(_get_utf8(raw_data, 'h_rcvd_amt'))

        self.car_no = _get_utf8(raw_data, 'h_srcar_no')
        self.seat_no = _get_utf8(raw_data, 'h_seat_no')

    def __repr__(self):
        repr_str = super(Train, self).__repr__()

        repr_str += " => %s호" % self.car_no

        if int(self.seat_no_count) != 1:
            repr_str += " %s~%s" % (self.seat_no, self.seat_no_end)
        else:
            repr_str += " %s" % self.seat_no

        repr_str += ", %s원" % self.price

        return repr_str

    def get_ticket_no(self):
        return "-".join(map(str, (self.sale_info1, self.sale_info2, self.sale_info3, self.sale_info4)))

    @property
    def fingerprint(self):
        """Stable, non-secret identifier suitable for confirmations and logs."""
        material = "\x1f".join(map(str, (
            self.sale_info1, self.sale_info2, self.sale_info3,
            self.dep_code, self.arr_code, self.dep_date, self.dep_time,
        )))
        return hashlib.sha256(material.encode('utf-8')).hexdigest()[:16]


class Passenger:
    """승객. Passenger List를 검색과 예약에 쓰도록 한다."""
    typecode = None  # txtPsgTpCd1    : '1',   #손님 종류 (어른 1, 어린이 3)
    discount_type = '000'  # txtDiscKndCd1  : '000', #할인 타입 (경로, 동반유아, 군장병 등..)
    count = 1  # txtCompaCnt1   : '1',   #인원수
    card = ''  # txtCardCode_1  : '',    #할인카드 종류
    card_no = ''  # txtCardNo_1    : '',    #할인카드 번호
    card_pw = ''  # txtCardPw_1    : '',    #할인카드 비밀번호

    @staticmethod
    def reduce(passenger_list):
        """Reduce passenger's list."""
        if list(filter(lambda x: not isinstance(x, Passenger), passenger_list)):
            raise TypeError("Passengers must be based on Passenger")

        groups = itertools.groupby(passenger_list, lambda x: x.group_key())
        return list(filter(lambda x: x.count > 0, [reduce(lambda a, b: a + b, g) for k, g in groups]))

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Passenger is abstract class. Do not make instance.")

    def __init_internal__(self, typecode, count=1, discount_type='000', card='', card_no='', card_pw=''):
        self.typecode = typecode
        self.count = count
        self.discount_type = discount_type
        self.card = card
        self.card_no = card_no
        self.card_pw = card_pw

    def __add__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError(
                "other's class(%s) is not equal to self's class(%s)." % (other.__class__, self.__class__))
        if self.group_key() == other.group_key():
            return self.__class__(count=self.count + other.count, discount_type=self.discount_type, card=self.card,
                                  card_no=self.card_no, card_pw=self.card_pw)
        else:
            raise TypeError(
                "other's group_key(%s) is not equal to self's group_key(%s)." % (other.group_key(), self.group_key()))

    def group_key(self):
        """get group string from attributes except count"""
        return "%s_%s_%s_%s_%s" % (self.typecode, self.discount_type, self.card, self.card_no, self.card_pw)

    def get_dict(self, index):
        assert isinstance(index, int)
        index = str(index)
        return {
            'txtPsgTpCd' + index: self.typecode,
            'txtDiscKndCd' + index: self.discount_type,
            'txtCompaCnt' + index: self.count,
            'txtCardCode_' + index: self.card,
            'txtCardNo_' + index: self.card_no,
            'txtCardPw_' + index: self.card_pw,
        }


# noinspection PyMissingConstructor
class AdultPassenger(Passenger):
    def __init__(self, count=1, discount_type='000', card='', card_no='', card_pw=''):
        Passenger.__init_internal__(self, '1', count, discount_type, card, card_no, card_pw)


# noinspection PyMissingConstructor
class ChildPassenger(Passenger):
    def __init__(self, count=1, discount_type='000', card='', card_no='', card_pw=''):
        Passenger.__init_internal__(self, '3', count, discount_type, card, card_no, card_pw)


# noinspection PyMissingConstructor
class ToddlerPassenger(Passenger):
    def __init__(self, count=1, discount_type='321', card='', card_no='', card_pw=''):
        Passenger.__init_internal__(self, '3', count, discount_type, card, card_no, card_pw)


# noinspection PyMissingConstructor
class SeniorPassenger(Passenger):
    def __init__(self, count=1, discount_type='131', card='', card_no='', card_pw=''):
        Passenger.__init_internal__(self, '1', count, discount_type, card, card_no, card_pw)


# noinspection PyMissingConstructor
class NCardPassenger(AdultPassenger):
    def __init__(self, count=1, card_no='', card='', card_pw='', discount_type=NCARD_DISCOUNT_CODE):
        AdultPassenger.__init__(self, count, discount_type, card, card_no, card_pw)


class TrainType:
    KTX = "100"  # "KTX, KTX-산천",
    SAEMAEUL = "101"  # "새마을호",
    MUGUNGHWA = "102"  # "무궁화호",
    TONGGUEN = "103"  # "통근열차",
    NURIRO = "102"  # "누리로",
    ALL = "109"  # "전체",
    AIRPORT = "105"  # "공항직통",
    KTX_SANCHEON = "100"  # "KTX-산천",
    ITX_SAEMAEUL = "101"  # "ITX-새마을",
    ITX_CHEONGCHUN = "104"  # "ITX-청춘",

    def __init__(self):
        raise NotImplementedError("Do not make instance.")


class ReserveOption:
    GENERAL_FIRST = "GENERAL_FIRST"  # 일반실 우선
    GENERAL_ONLY = "GENERAL_ONLY"  # 일반실만
    SPECIAL_FIRST = "SPECIAL_FIRST"  # 특실 우선
    SPECIAL_ONLY = "SPECIAL_ONLY"  # 특실만

    def __init__(self):
        raise NotImplementedError("Do not make instance.")


class NCardSeatType:
    GENERAL = "015"
    FREE = "003"

    def __init__(self):
        raise NotImplementedError("Do not make instance.")


class CardPaymentConfig(object):
    """Personal-card credentials for a lump-sum ticket payment.

    The representation is deliberately redacted because every value supplied to
    this object is payment authentication data.
    """

    def __init__(self, card_number, expiry, password2, birthdate6,
                 expected_amount):
        self.card_number = card_number
        self.expiry = expiry
        self.password2 = password2
        self.birthdate6 = birthdate6
        self.expected_amount = expected_amount

    def __repr__(self):
        return "<CardPaymentConfig redacted>"


class PaymentContext(object):
    """Non-secret values returned by a reservation and required for payment."""

    def __init__(self, pnr_no, wct_no, job_sqno1, job_sqno2,
                 rsv_chg_no, amount):
        self.pnr_no = pnr_no
        self.wct_no = wct_no
        self.job_sqno1 = job_sqno1
        self.job_sqno2 = job_sqno2
        self.rsv_chg_no = rsv_chg_no
        self.amount = amount

    def __repr__(self):
        return "<PaymentContext pnr_no=%r amount=%r>" % (
            self.pnr_no, self.amount,
        )


class AmbiguousTicketChangeError(Exception):
    """The server may have processed a one-shot ticket-change request.

    The response body is never attached. The in-process context blocks common
    serialization and keeps its representation redacted because it contains
    ticket credentials. Callers must inspect their tickets before deciding on
    any further action.
    """

    def __init__(self, context=None):
        self.context = context
        Exception.__init__(
            self,
            "ticket-change result is ambiguous; inspect tickets before retrying",
        )


class _TicketChangeKey(object):
    __slots__ = ('wct_no', 'sale_date', 'sale_sqno', 'return_password')

    def __init__(self, ticket):
        self.wct_no = ticket.sale_info1
        self.sale_date = ticket.sale_info2
        self.sale_sqno = ticket.sale_info3
        self.return_password = ticket.sale_info4

    def __repr__(self):
        return "<_TicketChangeKey redacted>"

    def __copy__(self):
        raise TypeError("_TicketChangeKey cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("_TicketChangeKey cannot be copied")

    def __getstate__(self):
        raise TypeError("_TicketChangeKey cannot be serialized")

    def __reduce__(self):
        raise TypeError("_TicketChangeKey cannot be serialized")


def _ticket_change_request_digest(items):
    return hashlib.sha256(repr(tuple(items)).encode('utf-8')).hexdigest()


class _TicketChangeRequest(object):
    """Hash-bound immutable request snapshot containing ticket credentials."""

    __slots__ = ('_items', '_digest')

    def __init__(self, data):
        if not isinstance(data, dict):
            raise TypeError("ticket-change request data must be a dict")
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(
                    "ticket-change form keys and values must be flat strings")
        items = tuple(sorted(data.items()))
        object.__setattr__(self, '_items', items)
        object.__setattr__(self, '_digest', _ticket_change_request_digest(items))

    def __setattr__(self, name, value):
        raise AttributeError("_TicketChangeRequest is read-only")

    @property
    def digest(self):
        return self._digest

    def to_dict(self, expected_digest):
        if (not isinstance(self._items, tuple) or
                self._digest != expected_digest or
                _ticket_change_request_digest(self._items) != expected_digest):
            raise ValueError("ticket-change request snapshot was modified")
        return dict(self._items)

    def __repr__(self):
        return "<_TicketChangeRequest redacted>"

    def __copy__(self):
        raise TypeError("_TicketChangeRequest cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("_TicketChangeRequest cannot be copied")

    def __getstate__(self):
        raise TypeError("_TicketChangeRequest cannot be serialized")

    def __reduce__(self):
        raise TypeError("_TicketChangeRequest cannot be serialized")


class _TicketChangeMalformedResponse(Exception):
    pass


class TicketChangeQuote(object):
    """Fare difference returned by Korail's temporary change operation."""

    __slots__ = ('original_amount', 'new_amount', 'additional_charge',
                 'refund_amount', '_locked')

    def __init__(self, original_amount, new_amount, additional_charge,
                 refund_amount):
        object.__setattr__(self, 'original_amount', original_amount)
        object.__setattr__(self, 'new_amount', new_amount)
        object.__setattr__(self, 'additional_charge', additional_charge)
        object.__setattr__(self, 'refund_amount', refund_amount)
        object.__setattr__(self, '_locked', True)

    def __setattr__(self, name, value):
        if getattr(self, '_locked', False):
            raise AttributeError("TicketChangeQuote is read-only")
        object.__setattr__(self, name, value)

    def __repr__(self):
        return ("<TicketChangeQuote original_amount=%r new_amount=%r "
                "additional_charge=%r refund_amount=%r>") % (
                    self.original_amount, self.new_amount,
                    self.additional_charge, self.refund_amount,
                )


class TicketChangeApproval(object):
    """Exact user-approved source, target, and fare-difference snapshot."""

    def __init__(self, source_fingerprint, target_fingerprint,
                 original_amount, new_amount, additional_charge,
                 refund_amount):
        self.source_fingerprint = source_fingerprint
        self.target_fingerprint = target_fingerprint
        self.original_amount = original_amount
        self.new_amount = new_amount
        self.additional_charge = additional_charge
        self.refund_amount = refund_amount


class TicketChangeResult(object):
    def __init__(self, source_fingerprint, target_fingerprint, quote,
                 status, payment_required, payment_flag=None,
                 pre_settlement_flag=None):
        self.source_fingerprint = source_fingerprint
        self.target_fingerprint = target_fingerprint
        self.quote = _copy_ticket_change_quote(quote)
        self.status = status
        self.payment_required = payment_required
        self.payment_flag = payment_flag
        self.pre_settlement_flag = pre_settlement_flag
        self.settlement_submitted = False
        self.card_charge_submitted = False
        self.ticket_verified = False

    def __repr__(self):
        return "<TicketChangeResult status=%r target=%r>" % (
            self.status, self.target_fingerprint,
        )


class TicketChangeContext(object):
    """One-shot mutable state for one issued-ticket change.

    This object intentionally cannot be serialized: it contains the return
    password required by Korail, while its representation remains redacted.
    """

    __slots__ = (
        'source_fingerprint', 'target_fingerprint', '_quote', 'state',
        '_key', '_request', '_request_digest', '_temporary_pnr',
        '_lump_settlement_target', '_payment_flag', '_pre_settlement_flag',
        '_prepare_attempted', '_reprice_attempted', '_settle_attempted',
        '_rollback_attempted', '_approved_snapshot',
    )

    def __init__(self, source_fingerprint, target_fingerprint, key,
                 request_data):
        self.source_fingerprint = source_fingerprint
        self.target_fingerprint = target_fingerprint
        self._quote = None
        self.state = 'NEW'
        self._key = key
        if not isinstance(request_data, _TicketChangeRequest):
            raise TypeError("request_data must be a _TicketChangeRequest")
        self._request = request_data
        self._request_digest = request_data.digest
        self._temporary_pnr = None
        self._lump_settlement_target = None
        self._payment_flag = None
        self._pre_settlement_flag = None
        self._prepare_attempted = False
        self._reprice_attempted = False
        self._settle_attempted = False
        self._rollback_attempted = False
        self._approved_snapshot = None

    @property
    def quote(self):
        if self._quote is None:
            return None
        return _copy_ticket_change_quote(self._quote)

    def __copy__(self):
        raise TypeError("TicketChangeContext cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("TicketChangeContext cannot be copied")

    def __reduce__(self):
        raise TypeError("TicketChangeContext cannot be serialized")

    def __getstate__(self):
        raise TypeError("TicketChangeContext cannot be serialized")

    def safe_summary(self):
        return {
            'source_fingerprint': self.source_fingerprint,
            'target_fingerprint': self.target_fingerprint,
            'state': self.state,
        }

    def __repr__(self):
        return ("<TicketChangeContext source=%r target=%r state=%r "
                "credentials=redacted>") % (
                    self.source_fingerprint, self.target_fingerprint,
                    self.state,
                )


def _config_value(config, name, aliases=(), default=None):
    if isinstance(config, dict):
        for key in (name,) + tuple(aliases):
            if key in config:
                return config[key]
        return default
    for key in (name,) + tuple(aliases):
        if hasattr(config, key):
            return getattr(config, key)
    return default


def _payment_digits(config, name, aliases, length):
    value = _config_value(config, name, aliases)
    if (not isinstance(value, str) or len(value) != length or
            re.match(r'^[0-9]+$', value) is None):
        raise ValueError("%s must be exactly %d digits" % (name, length))
    return value


def _payment_card_number(config):
    value = _config_value(config, 'card_number', ('card_no',))
    if (not isinstance(value, str) or not 13 <= len(value) <= 19 or
            re.match(r'^[0-9]+$', value) is None):
        raise ValueError("card_number must be 13 to 19 digits")
    checksum = 0
    parity = len(value) % 2
    for index, char in enumerate(value):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    if checksum % 10 != 0:
        raise ValueError("card_number checksum is invalid")
    return value


def _payment_context_from_response(data):
    jrny_infos = data.get('jrny_infos') or {}
    journeys = jrny_infos.get('jrny_info') or []
    first_journey = journeys[0] if journeys else {}
    # KorailTalk 6.5.0 calculates the charge by summing h_rcvd_amt for every
    # seat in every journey. Prefer that exact calculation over response-level
    # totals, which are not used by the app's card-payment screen.
    received_amounts = []
    for journey in journeys:
        seat_infos = journey.get('seat_infos') or {}
        for seat in seat_infos.get('seat_info') or []:
            value = _get_utf8(seat, 'h_rcvd_amt')
            try:
                received_amounts.append(int(value))
            except (TypeError, ValueError):
                received_amounts = []
                break
        if not received_amounts and (seat_infos.get('seat_info') or []):
            break
    amount = sum(received_amounts) if received_amounts else None
    if amount is None:
        amount = _get_first(data, ('h_tot_rcvd_amt', 'h_rsv_amt'))
    if amount is None:
        # ReservationPayment uses the final received amount; reservation-list
        # responses expose the same value as h_rsv_amt.
        amount = _get_utf8(data, 'price')
    return PaymentContext(
        _get_utf8(data, 'h_pnr_no'),
        _get_utf8(data, 'h_wct_no'),
        _get_utf8(data, 'h_tmp_job_sqno1'),
        _get_utf8(data, 'h_tmp_job_sqno2'),
        _get_first(first_journey, ('h_rsv_chg_no', 'hidRsvChgNo')),
        amount,
    )


def _payment_context_is_complete(context):
    if not isinstance(context, PaymentContext):
        return False
    required = (
        context.pnr_no,
        context.wct_no,
        context.job_sqno1,
        context.rsv_chg_no,
    )
    if any(value is None or value == '' for value in required):
        return False
    # The app always submits the second temporary-job field. An empty value is
    # valid for some reservation shapes, but a missing field is not.
    if context.job_sqno2 is None:
        return False
    try:
        return int(context.amount) > 0
    except (TypeError, ValueError):
        return False


def _build_card_payment_payload(payment_context, config):
    """Build the 6.5.0 ReservationPayment form without performing I/O."""
    context = payment_context
    if isinstance(context, dict):
        context = _payment_context_from_response(context)
    elif isinstance(context, Reservation):
        context = context.payment_context
    if not isinstance(context, PaymentContext):
        raise ValueError("payment_context is required")

    context_values = (
        ('pnr_no', context.pnr_no),
        ('wct_no', context.wct_no),
        ('job_sqno1', context.job_sqno1),
        ('rsv_chg_no', context.rsv_chg_no),
    )
    for field, value in context_values:
        if value is None or value == '':
            raise ValueError("payment context is missing %s" % field)
    if context.job_sqno2 is None:
        raise ValueError("payment context is missing job_sqno2")

    try:
        amount = int(context.amount)
    except (TypeError, ValueError):
        raise ValueError("payment context amount must be a positive integer")
    if amount <= 0:
        raise ValueError("payment context amount must be a positive integer")

    expected_amount = _config_value(config, 'expected_amount')
    if expected_amount is None:
        raise ValueError("expected_amount is required")
    try:
        expected_amount = int(expected_amount)
    except (TypeError, ValueError):
        raise ValueError("expected_amount must be a positive integer")
    if expected_amount <= 0:
        raise ValueError("expected_amount must be a positive integer")
    if expected_amount != amount:
        raise ValueError("reservation amount does not match expected_amount")

    card_number = _payment_card_number(config)
    expiry = _payment_digits(
        config, 'expiry', ('card_expiry', 'valid_thru'), 4,
    )
    if not 1 <= int(expiry[2:]) <= 12:
        raise ValueError("expiry month must be between 01 and 12")
    password2 = _payment_digits(
        config, 'password2', ('card_password', 'password'), 2,
    )
    birthdate6 = _payment_digits(
        config, 'birthdate6', ('birthdate', 'birth_date'), 6,
    )

    return {
        'hidPnrNo': context.pnr_no,
        'hidWctNo': context.wct_no,
        'hidTmpJobSqno1': context.job_sqno1,
        'hidTmpJobSqno2': context.job_sqno2,
        'hidRsvChgNo': context.rsv_chg_no,
        'hidInrecmnsGridcnt': '1',
        'hidStlMnsSqno1': '1',
        'hidStlMnsCd1': '02',
        'hidMnsStlAmt1': str(amount),
        'hidCrdInpWayCd1': '@',
        'hidStlCrCrdNo1': card_number,
        'hidVanPwd1': password2,
        'hidCrdVlidTrm1': expiry,
        'hidIsmtMnthNum1': '0',
        'hidAthnDvCd1': 'J',
        'hidAthnVal1': birthdate6,
        'hiduserYn': 'Y',
    }


def _ticket_change_target_fingerprint(train, seat_attribute):
    material = "\x1f".join(map(str, (
        train.train_type, train.train_group, train.train_no, train.run_date,
        train.dep_code, train.dep_date, train.dep_time,
        train.arr_code, train.arr_date, train.arr_time, seat_attribute,
        train.dep_station_cons_order, train.dep_station_run_order,
        train.arr_station_cons_order, train.arr_station_run_order,
    )))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()[:16]


def _ticket_change_amount(value, field):
    try:
        amount = int(value)
    except (TypeError, ValueError):
        raise _TicketChangeMalformedResponse(field)
    if amount < 0:
        raise _TicketChangeMalformedResponse(field)
    return amount


def _ticket_change_quote_tuple(quote):
    return (
        quote.original_amount, quote.new_amount,
        quote.additional_charge, quote.refund_amount,
    )


def _copy_ticket_change_quote(quote):
    return TicketChangeQuote(*_ticket_change_quote_tuple(quote))


def _ticket_change_quote(response):
    quote = TicketChangeQuote(
        _ticket_change_amount(response.get('ogtkRcvdAmt'), 'ogtkRcvdAmt'),
        _ticket_change_amount(response.get('h_tot_rcvd_amt'), 'h_tot_rcvd_amt'),
        _ticket_change_amount(response.get('scnIndcAmt'), 'scnIndcAmt'),
        _ticket_change_amount(response.get('totRetAmt'), 'totRetAmt'),
    )
    expected_charge = max(quote.new_amount - quote.original_amount, 0)
    expected_refund = max(quote.original_amount - quote.new_amount, 0)
    if (quote.additional_charge != expected_charge or
            quote.refund_amount != expected_refund):
        raise KorailError("ticket-change response amounts are inconsistent", None)
    return quote


def _ticket_change_lump_target(response):
    if not isinstance(response, dict):
        raise KorailError("ticket-change response must be an object", None)
    journey_wrapper = response.get('jrny_infos') or {}
    if not isinstance(journey_wrapper, dict):
        raise KorailError("ticket-change response must contain one journey", None)
    journeys = journey_wrapper.get('jrny_info') or []
    if isinstance(journeys, dict):
        journeys = [journeys]
    if (not isinstance(journeys, list) or len(journeys) != 1 or
            not isinstance(journeys[0], dict)):
        raise KorailError("ticket-change response must contain one journey", None)
    target = _get_first(journeys[0], ('lumpStlTgtNo', 'h_lump_stl_tgt_no'))
    if not isinstance(target, str) or not target.strip():
        raise KorailError("ticket-change response has no settlement target", None)
    return target


def _ticket_change_original_ticket(response):
    if not isinstance(response, dict):
        raise KorailError("ticket-change original response must be an object", None)
    tickets = response.get('orgTkList')
    if tickets is None:
        tickets = (response.get('org_tk_infos') or {}).get('org_tk_info')
    if isinstance(tickets, dict):
        tickets = [tickets]
    if not isinstance(tickets, list) or len(tickets) != 1:
        raise KorailError("ticket-change supports exactly one original ticket", None)
    ticket = tickets[0]
    if not isinstance(ticket, dict):
        raise KorailError("ticket-change original ticket is malformed", None)
    journeys = ticket.get('jrnyList') or []
    companions = ticket.get('cmpnList') or []
    if isinstance(journeys, dict):
        journeys = [journeys]
    if isinstance(companions, dict):
        companions = [companions]
    if (not isinstance(journeys, list) or not isinstance(companions, list) or
            len(journeys) != 1 or len(companions) != 1 or
            not isinstance(journeys[0], dict) or
            not isinstance(companions[0], dict)):
        raise KorailError(
            "ticket-change supports one direct journey and one passenger", None,
        )
    return ticket, journeys[0], companions[0]


class Reservation(Train):
    """Revervation object"""

    # : 예약번호
    rsv_id = None  # h_pnr_no

    # : 여정 번호
    journey_no = None  # txtJrnySqno

    #: 여정 카운트
    journey_cnt = None  # txtJrnyCnt

    #: 예약변경 번호?
    rsv_chg_no = "00000"

    #: 자리 갯수
    seat_no_count = None  # h_tot_seat_cnt  ex) 001

    #: 결제 기한 날짜
    buy_limit_date = None  # h_ntisu_lmt_dt

    #: 결제 기한 시간
    buy_limit_time = None  # h_ntisu_lmt_tm

    #: 예약 가격
    price = None  # h_rsv_amt  ex) 00013900

    #: 열차 번호 (Not implemented)
    car_no = None  # h_srcar_no

    #: 자리 번호 (Not implemented)
    seat_no = None  # h_seat_no

    #: 자리 번호 (Not implemented)
    seat_no_end = None  # h_seat_no_end

    def __init__(self, data):
        super(Reservation, self).__init__(data)
        self.payment_context = None
        # 이 두 필드가 결과에 빠져있음
        self.dep_date = _get_utf8(data, 'h_run_dt')
        self.arr_date = _get_utf8(data, 'h_run_dt')

        self.rsv_id = _get_utf8(data, 'h_pnr_no')
        self.seat_no_count = int(_get_utf8(data, 'h_tot_seat_cnt'))
        self.buy_limit_date = _get_utf8(data, 'h_ntisu_lmt_dt')
        self.buy_limit_time = _get_utf8(data, 'h_ntisu_lmt_tm')
        self.price = int(_get_utf8(data, 'h_rsv_amt'))
        self.journey_no = _get_utf8(data, 'txtJrnySqno', "001")
        self.journey_cnt = _get_utf8(data, 'txtJrnyCnt', "01")
        self.rsv_chg_no = _get_utf8(data, 'hidRsvChgNo', "00000")


        # 좌석정보 추가 업데이트 필요.
        # self.car_no = None
        # self.seat_no = None
        # self.seat_no_end = None



    def __repr__(self):
        repr_str = super(Reservation, self).__repr__()

        repr_str += ", %s원(%s석)" % (self.price, self.seat_no_count)

        buy_limit_time = "%s:%s" % (self.buy_limit_time[:2], self.buy_limit_time[2:4])

        buy_limit_date = "%s월 %s일" % (int(self.buy_limit_date[4:6]), int(self.buy_limit_date[6:]))

        repr_str += ", 구입기한 %s %s" % (buy_limit_date, buy_limit_time)

        return repr_str


class ExceptionForm(type):
    codes = set()

    def __contains__(cls, item):
        return item in cls.codes


class KorailError(with_metaclass(ExceptionForm, Exception)):
    """Korail Base Error Class"""

    def __init__(self, msg, code):
        self.msg = msg
        self.code = code

    def __str__(self):
        return "%s (%s)" % (self.msg, self.code)


class NeedToLoginError(KorailError):
    """Korail NeedToLogin Error Class"""
    codes = {'P058'}

    def __init__(self, code=None):
        KorailError.__init__(self, "Need to Login", code)


class NoResultsError(KorailError):
    """Korail NoResults Error Class"""
    codes = {'P100',
             'WRG000000',
             'WRD000061',  # 직통열차는 없지만, 환승으로 조회 가능합니다.
             'WRT300005'
    }

    def __init__(self, code=None):
        KorailError.__init__(self, "No Results", code)


class SoldOutError(KorailError):
    codes = {'ERR211161'}

    def __init__(self, code=None):
        KorailError.__init__(self, "Sold out", code)


# noinspection PyUnresolvedReferences,PyRedeclaration
class Korail(object):
    """Korail object"""
    _session = None

    _device, _version = 'AD', '250601002'
    _sid_key = b"2485dd54d9deaa36"
    _device_id = "558a4f02041657ea"
    _key = 'korail1234567890'

    _idx = None

    membership_number = None
    name = None
    email = None

    def __init__(self, korail_id, korail_pw, auto_login=True, want_feedback=False):
        self._session = requests.session()
        self._session.headers.update({'User-Agent': DEFAULT_USER_AGENT})
        self._engine = DynaPathMasterEngine()
        self.korail_id = korail_id
        self.korail_pw = korail_pw
        self.want_feedback = want_feedback
        self.logined = False
        if auto_login:
            self.login(korail_id, korail_pw)

    def _generate_sid(self, ts):
        plaintext = (f"{self._device}{ts}").encode('utf-8')
        cipher = AES.new(self._sid_key, AES.MODE_CBC, iv=self._sid_key)
        return base64.b64encode(cipher.encrypt(pad(plaintext, 16))).decode('utf-8') + "\n"

    def _get_auth_headers_and_sid(self, url):
        headers = {}
        sid = None
        if any(path in url for path in DYNAPATH_PATHS):
            ts = int(time.time() * 1000)
            rand = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            token = self._engine.generate_token(self._device_id, ts, rand)
            headers['x-dynapath-m-token'] = token
            sid = self._generate_sid(ts)
        return headers, sid

    def __enc_password(self, password):
        url = KORAIL_CODE
        data = {
            'code': "app.login.cphd"
        }

        r = self._session.post(url, data=data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        if j['strResult'] == 'SUCC' and j.get('app.login.cphd') is not None:
            self._idx = j['app.login.cphd']['idx']
            key = j['app.login.cphd']['key']

            encrypt_key = key.encode(encoding='utf-8', errors='strict')
            iv = key[:16].encode(encoding='utf-8', errors='strict')
            cipher = AES.new(encrypt_key, AES.MODE_CBC, iv)

            padded_data = pad(password.encode("utf-8"), AES.block_size)

            return base64.b64encode(base64.b64encode(cipher.encrypt(padded_data))).decode("utf-8")
        else:
            return False


    def login(self, korail_id=None, korail_pw=None):
        """Login to Korail server.
:param korail_id : `Korail membership number` or `phone number` or `email`
    membership   : xxxxxxxx (8 digits)
    phone number : xxx-xxxx-xxxx
    email        : xxx@xxx.xxx
:param korail_pw : Korail account korail_pw
:param auto_login=True :

First, you need to create a Korail object.

    >>> from korail2 import *
    >>> korail = Korail("12345678", YOUR_PASSWORD) # with membership number
    >>> korail = Korail("carpedm20@gmail.com", YOUR_PASSWORD) # with email
    >>> korail = Korail("010-9964-xxxx", YOUR_PASSWORD) # with phone number

If you do not want login automatically,

    >>> korail = Korail("12345678", YOUR_PASSWORD, auto_login=False)
    >>> korail.login()
    True

When you want change ID using existing object,

    >>> korail.login(ANOTHER_ID, ANOTHER_PASSWORD)
    True

"""
        if korail_id is None:
            korail_id = self.korail_id
        else:
            self.korail_id = korail_id

        if korail_pw is None:
            korail_pw = self.korail_pw
        else:
            self.korail_pw = korail_pw

        if EMAIL_REGEX.match(korail_id):
            txt_input_flg = '5'
        elif PHONE_NUMBER_REGEX.match(korail_id):
            txt_input_flg = '4'
        else:
            txt_input_flg = '2'

        url = KORAIL_LOGIN
        headers, sid = self._get_auth_headers_and_sid(url)

        data = {
            'Device': self._device,
            'Version': self._version, # HACK
            #'Version': self._version,
            # 2 : for membership number,
            # 4 : for phone number,
            # 5 : for email,
            'txtInputFlg': txt_input_flg,
            'txtMemberNo': korail_id,
            'txtPwd': self.__enc_password(korail_pw),
            'idx': self._idx
        }
        if sid:
            data['Sid'] = sid

        r = self._session.post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        if j['strResult'] == 'SUCC' and j.get('strMbCrdNo') is not None:
            self._key = j['Key']
            self.membership_number = j['strMbCrdNo']
            self.name = j['strCustNm']
            self.email = j['strEmailAdr']
            self.logined = True
            return True
        else:
            self.logined = False
            return False

    def logout(self):
        """Logout from Korail server"""
        url = KORAIL_LOGOUT
        self._session.get(url, timeout=REQUEST_TIMEOUT)
        self.logined = False

    def _result_check(self, j):
        """Result data check"""
        if self.want_feedback:
            print(j['h_msg_txt'])

        if j['strResult'] == 'FAIL':
            h_msg_cd = _get_utf8(j, 'h_msg_cd')
            h_msg_txt = _get_utf8(j, 'h_msg_txt')
            # P058 : 로그인 필요
            matched_error = list(filter(lambda x: h_msg_cd in x, (NoResultsError, NeedToLoginError, SoldOutError)))
            if matched_error:
                raise matched_error[0](h_msg_cd)
            else:
                raise KorailError(h_msg_txt, h_msg_cd)
        else:
            return True

    def search_train_allday(self, dep, arr, date=None, time=None, train_type=TrainType.ALL,
                            passengers=None, include_no_seats=False):
        """Search all trains for specific time and date."""
        min1 = timedelta(minutes=1)
        all_trains = []
        dep_time = time
        for i in range(15):  # 최대 15번 호출
            try:
                trains = self.search_train(dep, arr, date, dep_time, train_type, passengers, True)
                all_trains.extend(trains)
                # 만약 마지막 승차권의 출발시각이 23시 59분인 경우, 검색 중지. (다음 날 승차권 검색 방지)
                last_dep_time = datetime.strptime(all_trains[-1].dep_time, "%H%M%S")
                if (last_dep_time.hour == 23) & (last_dep_time.minute == 59):
                    break
                # 마지막 열차시간에 1분 더해서 계속 검색.
                t = last_dep_time + min1
                dep_time = t.strftime("%H%M%S")
            except NoResultsError:
                break

        if not include_no_seats:
            all_trains = list(filter(lambda x: x.has_seat(), all_trains))

        if len(all_trains) == 0:
            raise NoResultsError()

        return all_trains

    def search_train(self, dep, arr, date=None, time=None, train_type=TrainType.ALL,
                     passengers=None, include_no_seats=False, include_waiting_list=False):
        """Search trains for specific time and date.

:param dep: A departure station in Korean  ex) '서울'
:param arr: A arrival station in Korean  ex) '부산'
:param date: (optional) A departure date in `yyyyMMdd` format
:param time: (optional) A departure time in `hhmmss` format
:param train_type: (optional) A type of train
                   - 00: KTX, KTX-산천
                   - 01: 새마을호
                   - 02: 무궁화호
                   - 03: 통근열차
                   - 04: 누리로
                   - 05: 전체 (기본값)
                   - 06: 공학직통
                   - 07: KTX-산천
                   - 08: ITX-새마을
                   - 09: ITX-청춘
:param passengers=None: (optional) List of Passenger Objects. None means 1 AdultPassenger.
:param include_no_seats=False: (optional) When True, a result includes trains which has no seats.
:param include_waiting_list=False: (optional) When False, a result includes trains which has no seats but can make a wait reservation(예약 대기)'
"""
        # 코레일에 열차 티켓 리스트 API 요청시 한국시간을 기준으로 함.
        kst_now = datetime.utcnow() + timedelta(hours=9)
        if date is None:
            date = kst_now.strftime("%Y%m%d")
        if time is None:
            time = kst_now.strftime("%H%M%S")

        if passengers is None:
            passengers = [AdultPassenger()]

        passengers = Passenger.reduce(passengers)

        adult_count = reduce(lambda a, b: a + b.count, list(filter(lambda x: isinstance(x, AdultPassenger), passengers)), 0)
        child_count = reduce(lambda a, b: a + b.count, list(filter(lambda x: isinstance(x, ChildPassenger), passengers)), 0)
        toddler_count = reduce(lambda a, b: a + b.count, list(filter(lambda x: isinstance(x, ToddlerPassenger), passengers)), 0)
        senior_count = reduce(lambda a, b: a + b.count, list(filter(lambda x: isinstance(x, SeniorPassenger), passengers)), 0)

        url = KORAIL_SEARCH_SCHEDULE
        headers, sid = self._get_auth_headers_and_sid(url)
        data = {
            'Device': self._device,
            'radJobId': '1',
            'selGoTrain': train_type,
            'txtCardPsgCnt': '0',
            'txtGdNo': '',
            'txtGoAbrdDt': date,  # '20140803',
            'txtGoEnd': arr,
            'txtGoHour': time,  # '071500',
            'txtGoStart': dep,
            'txtJobDv': '',
            'txtMenuId': '11',
            'txtPsgFlg_1': adult_count,  # 어른
            'txtPsgFlg_2': child_count,  # 어린이
            'txtPsgFlg_8': toddler_count,  # 유아
            'txtPsgFlg_3': senior_count,  # 경로
            'txtPsgFlg_4': '0',  # 중증 장애인
            'txtPsgFlg_5': '0',  # 경증 장애인
            'txtSeatAttCd_2': '000',
            'txtSeatAttCd_3': '000',
            'txtSeatAttCd_4': '015',
            'txtTrnGpCd': train_type,

            'Version': self._version,
        }


        r = self._session.post(url, params=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        if self._result_check(j):
            train_infos = j['trn_infos']['trn_info']

            trains = []

            for info in train_infos:
                trains.append(Train(info))

            filter_fns = [lambda x: x.has_seat()]

            if include_no_seats:
                filter_fns.append(lambda x: not x.has_seat())

            if include_waiting_list:
                filter_fns.append(lambda x: x.has_waiting_list())

            trains = list(filter(lambda x: any(f(x) for f in filter_fns), trains))

            if len(trains) == 0:
                raise NoResultsError()

            return trains

    def search_ncard_trains(self, dep, arr, dcnt_card_kind_mg_no, use_psb_tno,
                            date=None, time=None, train_type=TrainType.ALL,
                            dcnt_card_kind_cd="MMM", use_trm_dno="",
                            qry_pg_no="1", dirt_chtn_dv_cd="1"):
        """Search N-card discounted ticket train candidates.

        `dcnt_card_kind_mg_no` and `use_psb_tno` come from the user's owned
        N-card metadata in KorailTalk. This method only searches candidates; it
        does not reserve or pay for a ticket.
        """
        kst_now = datetime.utcnow() + timedelta(hours=9)
        if date is None:
            date = kst_now.strftime("%Y%m%d")
        if time is None:
            time = "000000"

        url = KORAIL_NCARD_SCHEDULE_VIEW
        headers, sid = self._get_auth_headers_and_sid(url)
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'dptDt': date,
            'dptRsStnNm': dep,
            'arvRsStnNm': arr,
            'dptTm': time,
            'trnGpCd': train_type,
            'dirtChtnDvCd': dirt_chtn_dv_cd,
            'dcntCrdKndCd': dcnt_card_kind_cd,
            'dcntCrdKndMgNo': dcnt_card_kind_mg_no,
            'useTrmDno': use_trm_dno,
            'usePsbTno': use_psb_tno,
            'qryPgNo': qry_pg_no,
        }
        if sid:
            data['Sid'] = sid

        r = self._session.get(url, params=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        if self._result_check(j):
            train_infos = (
                j.get('trnScdlList') or
                j.get('trn_scdl_list') or
                j.get('trn_infos', {}).get('trn_info') or
                []
            )
            if isinstance(train_infos, dict):
                train_infos = [train_infos]

            trains = [NCardTrain(info) for info in train_infos]
            if train_type != TrainType.ALL:
                trains = [train for train in trains if train.train_group == train_type]
            if len(trains) == 0:
                raise NoResultsError()
            return trains

    def search_owned_ncard_trains(self, ncard, dep=None, arr=None, date=None, time=None,
                                  train_type=None, segment_index=0, passenger_count=1,
                                  room_class="9", seat_attribute=NCardSeatType.GENERAL,
                                  dirt_chtn_dv_cd="1", transfer_arrival=""):
        """Search discounted trains for an already-owned N-card.

        This mirrors KorailTalk's "My Ticket > Pass > N-card > Ticket booking"
        flow. It uses the owned N-card detail returned by :meth:`owned_ncards`
        and the seat-assignment schedule endpoint; it does not reserve or pay
        for a ticket.
        """
        kst_now = datetime.utcnow() + timedelta(hours=9)
        if date is None:
            date = kst_now.strftime("%Y%m%d")
        if time is None:
            time = "000000"

        segments = getattr(ncard, 'segments', None) or []
        if not segments:
            raise KorailError("N-card has no route segment metadata", None)
        segment = segments[segment_index]

        if dep is None:
            dep = _get_utf8(segment, 'dptRsStnNm') or ncard.dep_name
        if arr is None:
            arr = _get_utf8(segment, 'arvRsStnNm') or ncard.arr_name
        if train_type is None:
            train_type = _get_utf8(segment, 'trnGpCd') or TrainType.KTX

        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'menuId': NCARD_SEAT_ASSIGN_MENU_ID,
            'dptDt': date,
            'dptTm': time,
            'dptRsStnNm': dep,
            'arvRsStnNm': arr,
            'trnGpCd': train_type,
            'psrmClCd': room_class,
            'seatAttCd1': seat_attribute,
            'psgNum1': str(passenger_count),
            'stlbDturDvNm1': _get_utf8(segment, 'stlbDturDvNm') or '',
            'dirtChtnDvCd': dirt_chtn_dv_cd,
            'chtnArvRsStnNm': transfer_arrival,
        }

        r = self._session.post(KORAIL_SEAT_ASSIGN_SCHEDULE_VIEW, data=data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        if self._result_check(j):
            train_infos = (
                j.get('trn_infos', {}).get('trn_info') or
                j.get('trn_info') or
                []
            )
            if isinstance(train_infos, dict):
                train_infos = [train_infos]

            trains = [NCardTrain(info) for info in train_infos]
            for train in trains:
                if not train.seat_attribute:
                    train.seat_attribute = seat_attribute
            if train_type != TrainType.ALL:
                trains = [train for train in trains if train.train_group == train_type]
            if len(trains) == 0:
                raise NoResultsError()
            return trains

    def ncard_history(self, dcnt_card_no):
        """Return raw N-card usage history for an already known N-card number."""
        url = KORAIL_NCARD_USE_HISTORY
        headers, sid = self._get_auth_headers_and_sid(url)
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'dcntCrdNo': dcnt_card_no,
        }
        if sid:
            data['Sid'] = sid

        r = self._session.get(url, params=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        if self._result_check(j):
            return j

    def owned_ncards(self):
        """Return owned N-cards from KorailTalk's current-ticket list.

        KorailTalk shows purchased N-cards under "My Ticket > Commutation/Pass"
        using the same MyTicketList endpoint as ordinary tickets, then fetches
        details through SelTicketInfo. This method mirrors only that read-only
        lookup path.
        """
        list_data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'txtDeviceId': '',
            'txtIndex': '1',
            'h_page_no': '1',
            'h_abrd_dt_from': '',
            'h_abrd_dt_to': '',
            'hiduserYn': 'Y',
            'hidName': '',
            'hidTeleNo': '',
            'hidPwd': '',
            'tsRsStnCd': '',
        }
        r = self._session.post(KORAIL_MYTICKETLIST, data=list_data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)

        try:
            self._result_check(j)
        except NoResultsError:
            return []

        ncards = []
        for reservation in j.get('reservation_list', []):
            ticket_list = reservation.get('ticket_list') or []
            if not ticket_list:
                continue
            train_info = ticket_list[0].get('train_info') or []
            if not train_info:
                continue
            ticket_data = train_info[0]
            ticket_kind = _get_utf8(ticket_data, 'h_tk_knd_nm') or ''
            if _get_utf8(ticket_data, 'h_tk_knd_cd') != '81' and 'N카드' not in ticket_kind:
                continue

            detail_data = {
                'Device': self._device,
                'Version': self._version,
                'Key': self._key,
                'h_orgtk_ret_sale_dt': _get_utf8(ticket_data, 'h_orgtk_ret_sale_dt'),
                'h_orgtk_wct_no': _get_utf8(ticket_data, 'h_orgtk_wct_no'),
                'h_orgtk_sale_sqno': _get_utf8(ticket_data, 'h_orgtk_sale_sqno'),
                'h_orgtk_ret_pwd': _get_utf8(ticket_data, 'h_orgtk_ret_pwd'),
                'h_purchase_history': '',
            }
            detail_response = self._session.post(KORAIL_MYTICKET_SEAT, data=detail_data, timeout=REQUEST_TIMEOUT)
            detail = json.loads(detail_response.text)
            try:
                self._result_check(detail)
            except KorailError:
                detail = {}
            ncards.append(NCard(ticket_data, detail))

        return ncards

    def _select_reservation_seat_type(self, train, option, try_waiting):
        reserving_seat = True
        seat_type = None
        try:
            if train.has_seat() is False:
                raise SoldOutError()
            elif option == ReserveOption.GENERAL_ONLY:
                if train.has_general_seat():
                    seat_type = '1'
                else:
                    raise SoldOutError()
            elif option == ReserveOption.SPECIAL_ONLY:
                if train.has_special_seat():
                    seat_type = '2'
                else:
                    raise SoldOutError()
            elif option == ReserveOption.GENERAL_FIRST:
                if train.has_general_seat():
                    seat_type = '1'
                else:
                    seat_type = '2'
            elif option == ReserveOption.SPECIAL_FIRST:
                if train.has_special_seat():
                    seat_type = '2'
                else:
                    seat_type = '1'
        except SoldOutError as e:
            if try_waiting and option != ReserveOption.SPECIAL_ONLY and train.has_general_waiting_list():
                reserving_seat = False
                seat_type = '1'
            else:
                raise e
        return reserving_seat, seat_type

    def _build_reservation_data(self, train, passengers=None,
                                option=ReserveOption.GENERAL_FIRST,
                                try_waiting=False, seat_type_override=None):
        if seat_type_override is None:
            reserving_seat, seat_type = self._select_reservation_seat_type(train, option, try_waiting)
        else:
            reserving_seat, seat_type = True, seat_type_override

        if passengers is None:
            passengers = [AdultPassenger()]

        passengers = Passenger.reduce(passengers)
        cnt = reduce(lambda x, y: x + y.count, passengers, 0)
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'txtGdNo': '',
            'txtJobId': '1101' if reserving_seat else '1102',
            'txtTotPsgCnt': cnt,
            'txtSeatAttCd1': '000',
            'txtSeatAttCd2': '000',
            'txtSeatAttCd3': '000',
            'txtSeatAttCd4': '015',
            'txtSeatAttCd5': '000',
            'hidFreeFlg': 'N',
            'txtStndFlg': 'N',
            'txtMenuId': '11',
            'txtSrcarCnt': '0',
            'txtJrnyCnt': '1',

            # 이하 여정정보1
            'txtJrnySqno1': '001',
            'txtJrnyTpCd1': '11',
            'txtDptDt1': train.dep_date,
            'txtDptRsStnCd1': train.dep_code,
            'txtDptTm1': train.dep_time,
            'txtArvRsStnCd1': train.arr_code,
            'txtTrnNo1': train.train_no,
            'txtRunDt1': train.run_date,
            'txtTrnClsfCd1': train.train_type,
            'txtPsrmClCd1': seat_type,
            'txtTrnGpCd1': train.train_group,
            'txtChgFlg1': '',

            # 이하 여정정보2
            'txtJrnySqno2': '',
            'txtJrnyTpCd2': '',
            'txtDptDt2': '',
            'txtDptRsStnCd2': '',
            'txtDptTm2': '',
            'txtArvRsStnCd2': '',
            'txtTrnNo2': '',
            'txtRunDt2': '',
            'txtTrnClsfCd2': '',
            'txtPsrmClCd2': '',
            'txtChgFlg2': '',
        }

        index = 1
        for psg in passengers:
            data.update(psg.get_dict(index))
            index += 1
        return data

    def _select_ncard_seat_type(self, train, option, include_auxiliary=False):
        has_general = train.has_ncard_general_seat(include_auxiliary)
        has_special = train.has_ncard_special_seat()
        if option == ReserveOption.GENERAL_ONLY:
            if has_general:
                return '1'
        elif option == ReserveOption.SPECIAL_ONLY:
            if has_special:
                return '2'
        elif option == ReserveOption.GENERAL_FIRST:
            if has_general:
                return '1'
            if has_special:
                return '2'
        elif option == ReserveOption.SPECIAL_FIRST:
            if has_special:
                return '2'
            if has_general:
                return '1'
        raise SoldOutError()

    def build_ncard_reservation_payload(self, train, ncard_no,
                                        option=ReserveOption.GENERAL_FIRST,
                                        try_waiting=False):
        """Build, but do not submit, an N-card discounted reservation payload."""
        passengers = [NCardPassenger(card_no=ncard_no)]
        seat_attribute = train.seat_attribute or NCardSeatType.GENERAL
        seat_type_override = self._select_ncard_seat_type(
            train,
            option,
            include_auxiliary=(seat_attribute == NCardSeatType.FREE),
        )
        data = self._build_reservation_data(
            train, passengers, option, try_waiting,
            seat_type_override=seat_type_override,
        )
        data['txtMenuId'] = NCARD_SEAT_ASSIGN_MENU_ID
        data['txtSeatAttCd4'] = seat_attribute
        data.pop('txtSeatAttCd4_1', None)
        return data

    def reserve_owned_ncard(self, train, ncard_no,
                            option=ReserveOption.GENERAL_FIRST,
                            try_waiting=False):
        """Reserve a discounted ticket using an already-owned N-card."""
        url = KORAIL_TICKETRESERVATION
        headers, _ = self._get_auth_headers_and_sid(url)
        data = self.build_ncard_reservation_payload(
            train, ncard_no, option=option, try_waiting=try_waiting,
        )

        r = self._session.post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        if self._result_check(j):
            rsv_id = j['h_pnr_no']
            payment_context = _payment_context_from_response(j)
            for attempt in range(2):
                rsvlist = list(filter(lambda x: x.rsv_id == rsv_id, self.reservations()))
                if len(rsvlist) == 1:
                    reservation = rsvlist[0]
                    if payment_context.amount in (None, ''):
                        payment_context.amount = getattr(reservation, 'price', None)
                    reservation.payment_context = payment_context
                    return reservation
                if attempt == 0:
                    time.sleep(0.2)
            raise KorailError(
                "reservation %s was created but could not be reloaded" % rsv_id,
                None,
            )

    def pay_with_card(self, reservation, config):
        """Pay one reservation with a personal card, without automatic retries.

        If the reservation came from ``reservations()``, the missing one-time
        fields are loaded with a read-only ReservationList request first.
        ``config.expected_amount`` is mandatory so a fare change fails before
        this method sends the single payment request.
        """
        if not isinstance(reservation, Reservation):
            raise TypeError("reservation must be a Reservation")
        if (not _payment_context_is_complete(reservation.payment_context) or
                reservation.payment_context.pnr_no != reservation.rsv_id):
            reservation.payment_context = self.reservation_payment_context(
                reservation.rsv_id,
            )
        try:
            context_amount = int(reservation.payment_context.amount)
            reservation_amount = int(reservation.price)
        except (TypeError, ValueError):
            raise ValueError("reservation amount must be a positive integer")
        if context_amount <= 0 or reservation_amount <= 0:
            raise ValueError("reservation amount must be a positive integer")
        if context_amount != reservation_amount:
            raise ValueError("reservation and payment context amounts differ")
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
        }
        data.update(_build_card_payment_payload(reservation, config))

        # Do not retry this request automatically. A timeout or malformed
        # response can still mean the card was charged; verify tickets before
        # deciding what to do next.
        r = self._session.post(
            KORAIL_RESERVATION_PAYMENT,
            data=data,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )
        response = json.loads(r.text)
        self._result_check(response)
        return response

    def reservation_payment_context(self, reservation_id):
        """Read the one-time payment fields for an existing reservation."""
        if not isinstance(reservation_id, str) or not reservation_id:
            raise ValueError("reservation_id is required")
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'hidPnrNo': reservation_id,
        }
        r = self._session.get(KORAIL_RESERVATION_INQUIRY, params=data, timeout=REQUEST_TIMEOUT)
        response = json.loads(r.text)
        self._result_check(response)
        if _get_utf8(response, 'h_pnr_no') != reservation_id:
            raise KorailError("reservation inquiry returned a different PNR", None)
        context = _payment_context_from_response(response)
        if not _payment_context_is_complete(context):
            raise KorailError("reservation payment context is incomplete", None)
        return context

    def reserve(self, train, passengers=None, option=ReserveOption.GENERAL_FIRST, try_waiting=False):
        """Reserve a train.

:param train: An instance of `Train`.
:param passengers=None: (optional) List of Passenger Objects. None means 1 AdultPassenger.
:param option=ReserveOption.GENERAL_FIRST : (optional)

When tickets are not enough much for passengers, it raises SoldOutError.

If you want to select priority of seat grade, general or special,
There are 4 options in ReserveOption class.

- GENERAL_FIRST : Economic than Comfortable.
- GENERAL_ONLY  : Reserve only general seats. You are poorman ;-)
- SPECIAL_FIRST : Comfortable than Economic.
- SPECIAL_ONLY  : Richman.

:param option=try_waiting : (optional)

When the train allows waiting, enroll for the waiting list instead of failing in case there are no seats in the train.

        """

        url = KORAIL_TICKETRESERVATION
        headers, sid = self._get_auth_headers_and_sid(url)
        data = self._build_reservation_data(train, passengers, option, try_waiting)

        r = self._session.get(url, params=data, headers=headers, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        if self._result_check(j):
            rsv_id = j['h_pnr_no']
            rsvlist = list(filter(lambda x: x.rsv_id == rsv_id, self.reservations()))
            if len(rsvlist) == 1:
                return rsvlist[0]

    def _ticket_change_post(self, url, data, context=None, mutation=False):
        try:
            response = self._session.post(
                url, data=data, allow_redirects=False, timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            if context is not None:
                context.state = 'AMBIGUOUS'
            if mutation:
                raise AmbiguousTicketChangeError(context)
            raise KorailError("ticket-change read request failed", None)
        try:
            parsed = json.loads(response.text)
        except (TypeError, ValueError):
            if context is not None:
                context.state = 'AMBIGUOUS'
            if mutation:
                raise AmbiguousTicketChangeError(context)
            raise KorailError("ticket-change read response is malformed", None)
        if (not isinstance(parsed, dict) or
                parsed.get('strResult') not in ('SUCC', 'FAIL')):
            if context is not None:
                context.state = 'AMBIGUOUS'
            if mutation:
                raise AmbiguousTicketChangeError(context)
            raise KorailError("ticket-change read response is malformed", None)
        message = parsed.get('h_msg_txt')
        if parsed['strResult'] == 'SUCC':
            if not isinstance(message, str):
                if context is not None:
                    context.state = 'AMBIGUOUS'
                if mutation:
                    raise AmbiguousTicketChangeError(context)
                raise KorailError("ticket-change read response is malformed", None)
            if self.want_feedback:
                print(message)
            return parsed

        code = parsed.get('h_msg_cd')
        if not isinstance(code, str):
            code = None
        if self.want_feedback and isinstance(message, str):
            print(message)
        safe_message = message if isinstance(message, str) else (
            "ticket-change request failed")
        matched_error = list(filter(
            lambda error_type: code in error_type if code is not None else False,
            (NoResultsError, NeedToLoginError, SoldOutError),
        ))
        error = matched_error[0](code) if matched_error else KorailError(
            safe_message, code)
        if mutation and context is not None:
            context.state = 'EXPLICIT_FAILURE'
            pnr = parsed.get('h_pnr_no')
            if isinstance(pnr, str) and pnr.strip():
                context._temporary_pnr = pnr
            try:
                context._lump_settlement_target = (
                    _ticket_change_lump_target(parsed))
            except KorailError:
                pass
            error.context = context
        raise error

    def _ticket_change_ambiguous(self, context):
        context.state = 'AMBIGUOUS'
        raise AmbiguousTicketChangeError(context)

    def _ticket_change_key(self, ticket):
        if not isinstance(ticket, Ticket):
            raise TypeError("ticket must be a Ticket")
        key = _TicketChangeKey(ticket)
        for field, value in (
                ('ticket sale office number', key.wct_no),
                ('ticket sale date', key.sale_date),
                ('ticket sale sequence', key.sale_sqno),
                ('ticket return password', key.return_password)):
            _require_nonempty_str(value, field)
        return key

    def ticket_change_dates(self, ticket, trip_change_date=None):
        """Return dates allowed by Korail for an issued ticket change."""
        self._ticket_change_key(ticket)
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'tripChgDate': trip_change_date or ticket.dep_date,
        }
        response = self._ticket_change_post(
            KORAIL_TICKET_CHANGE_DATES, data,
        )
        dates = response.get('tripChgDates')
        if not isinstance(dates, list):
            raise KorailError("ticket-change date response is incomplete", None)
        return dates

    def _ticket_change_original(self, ticket):
        """Read the APK ticket-change DTO for exactly one issued ticket."""
        key = self._ticket_change_key(ticket)
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'tkCnt': '1',
            'ogtkSaleWctNo_1': key.wct_no,
            'ogtkSaleDd_1': key.sale_date,
            'ogtkSaleSqno_1': key.sale_sqno,
            'ogtkRetPwd_1': key.return_password,
        }
        response = self._ticket_change_post(
            KORAIL_TICKET_CHANGE_ORIGINAL, data,
        )
        _ticket_change_original_ticket(response)
        return response

    def _build_ticket_change_request(self, ticket, target, original_response,
                                     seat_attribute):
        if not isinstance(target, Train):
            raise TypeError("target must be a Train")
        if ticket.seat_no_count != 1:
            raise ValueError("ticket-change supports exactly one issued seat")
        if seat_attribute not in (NCardSeatType.GENERAL, NCardSeatType.FREE):
            raise ValueError("seat_attribute must be general (015) or free (003)")
        target_raw = getattr(target, 'raw', None)
        if not isinstance(target_raw, dict):
            raise ValueError("target schedule has no raw availability snapshot")
        general_code = _get_first(target_raw, ('h_gen_rsv_cd', 'genRsvCd'))
        free_code = _get_first(target_raw, ('h_free_rsv_cd', 'freeRsvCd'))
        if (seat_attribute == NCardSeatType.GENERAL and
                general_code not in ('11', '21')):
            raise ValueError("target does not offer a general seat")
        if (seat_attribute == NCardSeatType.FREE and
                (general_code != '13' or free_code != '11')):
            raise ValueError("target does not offer a free seat")

        key = self._ticket_change_key(ticket)
        required_source = (
            ('source train number', ticket.train_no),
            ('source run date', ticket.run_date),
            ('source departure code', ticket.dep_code),
            ('source departure date', ticket.dep_date),
            ('source departure time', ticket.dep_time),
            ('source arrival code', ticket.arr_code),
            ('source arrival date', ticket.arr_date),
            ('source arrival time', ticket.arr_time),
        )
        required_target = (
            ('target train class', target.train_type),
            ('target train group', target.train_group),
            ('target train number', target.train_no),
            ('target run date', target.run_date),
            ('target departure code', target.dep_code),
            ('target departure date', target.dep_date),
            ('target departure time', target.dep_time),
            ('target arrival code', target.arr_code),
            ('target arrival date', target.arr_date),
            ('target arrival time', target.arr_time),
            ('target departure construction order',
             target.dep_station_cons_order),
            ('target departure run order', target.dep_station_run_order),
            ('target arrival construction order', target.arr_station_cons_order),
            ('target arrival run order', target.arr_station_run_order),
        )
        for field, value in required_source + required_target:
            _require_nonempty_str(value, field)
        if ticket.dep_code != target.dep_code or ticket.arr_code != target.arr_code:
            raise ValueError("ticket-change route must remain unchanged")
        if (ticket.train_no, ticket.run_date, ticket.dep_date, ticket.dep_time,
                ticket.arr_date, ticket.arr_time) == (
                    target.train_no, target.run_date, target.dep_date,
                    target.dep_time, target.arr_date, target.arr_time):
            raise ValueError("ticket-change target is identical to the source")

        original, journey, companion = _ticket_change_original_ticket(
            original_response,
        )
        original_key_values = (
            _get_first(original, ('ogtkSaleWctNo', 'h_orgtk_wct_no')),
            _get_first(original, ('ogtkSaleDt', 'ogtkSaleDd', 'h_orgtk_ret_sale_dt')),
            _get_first(original, ('ogtkSaleSqno', 'h_orgtk_sale_sqno')),
            _get_first(original, ('ogtkRetPwd', 'h_orgtk_ret_pwd')),
        )
        for field, value in zip((
                'original sale office number', 'original sale date',
                'original sale sequence', 'original return password'),
                original_key_values):
            _require_nonempty_str(value, field)
        if original_key_values != (
                key.wct_no, key.sale_date, key.sale_sqno,
                key.return_password):
            raise KorailError("ticket-change original ticket does not match", None)

        original_dep = _get_first(journey, ('dptRsStnCd', 'h_dpt_rs_stn_cd'))
        original_arr = _get_first(journey, ('arvRsStnCd', 'h_arv_rs_stn_cd'))
        _require_nonempty_str(original_dep, 'original departure code')
        _require_nonempty_str(original_arr, 'original arrival code')
        journey_type_value = _get_first(journey, ('jrnyTpCd',))
        journey_type = _require_nonempty_str(
            journey_type_value, 'original journey type')
        if journey_type != '11':
            raise ValueError("ticket-change supports direct journeys only")
        if original_dep != target.dep_code or original_arr != target.arr_code:
            raise ValueError("ticket-change route must remain unchanged")
        original_class = _get_first(journey, ('stlbTrnClsfCd', 'h_trn_clsf_cd'))
        original_group = _get_first(journey, ('trnGpCd', 'h_trn_gp_cd'))
        _require_nonempty_str(original_class, 'original train class')
        _require_nonempty_str(original_group, 'original train group')
        if (original_class != target.train_type or
                original_group != target.train_group):
            raise ValueError("ticket-change train product must remain unchanged")

        passenger_type = _require_nonempty_str(
            _get_first(companion, ('psgTpDvCd',)),
            'original passenger type')
        discount_value = _get_first(companion, ('dcntKndCd',))
        discount_code = _require_nonempty_str(
            discount_value, 'original discount code')
        discount_number = _get_first(companion, ('dscpNo',), '')
        if passenger_type != '1':
            raise ValueError("ticket-change supports one adult passenger only")
        no_discount = discount_code == '000'
        ncard = discount_code == NCARD_DISCOUNT_CODE
        if not no_discount and not ncard:
            raise ValueError("ticket-change supports ordinary or N-card fares only")
        if ncard and not discount_number:
            raise ValueError("N-card discount number is missing")
        if ncard:
            _require_nonempty_str(discount_number, 'N-card discount number')

        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'trvlKndCd': '1',
            'totPrnb': '1',
            'isePrnb': '1',
            # NORMAL_FREE (003) is not the separate STANDING_SEAT (033).
            'stndSeatFlg': 'N',
            'intgTktIseFlg': 'N',
            'prcFareReCalcFlg': 'N',
            'alcSeatDmnPsDvCd': '000',
            'jrny2Cnt': '0000',
            'psg2Cnt': '0000',
            'jrnyCnt': '0001',
            'jrnySqno_1': '0001',
            'jrnyTpCd_1': '11',
            'trnNo_1': target.train_no.zfill(5),
            'runDt_1': target.run_date,
            'stlbTrnClsfCd_1': target.train_type,
            'trnGpCd_1': target.train_group,
            'dptDt_1': target.dep_date,
            'dptTm_1': target.dep_time,
            'dptRsStnCd_1': target.dep_code,
            'dptStnConsOrdr_1': target.dep_station_cons_order,
            'dptStnRunOrdr_1': target.dep_station_run_order,
            'arvDt_1': target.arr_date,
            'arvTm_1': target.arr_time,
            'arvRsStnCd_1': target.arr_code,
            'arvStnConsOrdr_1': target.arr_station_cons_order,
            'arvStnRunOrdr_1': target.arr_station_run_order,
            'seatCnt_1': '0001',
            'roomClsfCd_1_1': '1',
            'rqSeatAttCd_1_1': seat_attribute,
            'smkSeatAttCd_1_1': '000',
            'dirSeatAttCd_1_1': '000',
            'locSeatAttCd_1_1': '000',
            'etcSeatAttCd_1_1': '000',
            'psgCnt': '1',
            'psgInfoPerPrnb_1': '1',
            'psgTpDvCd_1': '1',
            'ortgCnt': '0001',
            'ogtkSaleWctNo_1': key.wct_no,
            'ogtkSaleDd_1': key.sale_date,
            'ogtkSaleSqno_1': key.sale_sqno,
            'ogtkRetPwd_1': key.return_password,
            'retNoMnlInpFlg_1': 'N',
            'dscpCnt_1': '0001' if ncard else '0000',
        }
        if ncard:
            data.update({
                'dcntKndCd_1_1': passenger_type + discount_code,
                'dscpNo_1_1': discount_number,
            })
        return data

    def prepare_ticket_change(self, ticket, target, expected_original_amount,
                              seat_attribute=None):
        """Create one temporary change and return its exact fare quote.

        This is a state-changing one-shot operation. The authoritative
        original-ticket DTO is always read immediately before the mutation.
        """
        try:
            expected_original_amount = int(expected_original_amount)
        except (TypeError, ValueError):
            raise ValueError("expected_original_amount must be a nonnegative integer")
        if expected_original_amount < 0:
            raise ValueError("expected_original_amount must be a nonnegative integer")
        if int(ticket.price) != expected_original_amount:
            raise ValueError("ticket amount does not match expected_original_amount")
        original_response = self._ticket_change_original(ticket)
        request_data = self._build_ticket_change_request(
            ticket, target, original_response, seat_attribute,
        )
        request_snapshot = _TicketChangeRequest(request_data)
        context = TicketChangeContext(
            ticket.fingerprint,
            _ticket_change_target_fingerprint(target, seat_attribute),
            self._ticket_change_key(ticket), request_snapshot,
        )
        if context._prepare_attempted:
            raise ValueError("ticket-change preparation was already attempted")
        context._prepare_attempted = True
        context.state = 'PREPARING'
        response = self._ticket_change_post(
            KORAIL_TICKET_CHANGE_RESERVATION,
            request_snapshot.to_dict(context._request_digest),
            context=context,
            mutation=True,
        )
        context._temporary_pnr = _get_utf8(response, 'h_pnr_no')
        if (not isinstance(context._temporary_pnr, str) or
                not context._temporary_pnr.strip()):
            self._ticket_change_ambiguous(context)
        try:
            context._lump_settlement_target = _ticket_change_lump_target(response)
        except KorailError:
            self._ticket_change_ambiguous(context)
        try:
            context._quote = _ticket_change_quote(response)
        except _TicketChangeMalformedResponse:
            self._ticket_change_ambiguous(context)
        except KorailError as error:
            context.state = 'PREPARE_MISMATCH'
            error.context = context
            raise
        if context._quote.original_amount != expected_original_amount:
            context.state = 'PREPARE_MISMATCH'
            error = KorailError("ticket-change original amount changed", None)
            error.context = context
            raise error
        context.state = 'PREPARED'
        return context

    def reprice_ticket_change(self, context, approval):
        """Approve the exact quote and perform the one-shot Y recalculation."""
        if not isinstance(context, TicketChangeContext):
            raise TypeError("context must be a TicketChangeContext")
        if not isinstance(approval, TicketChangeApproval):
            raise TypeError("approval must be a TicketChangeApproval")
        if context.state != 'PREPARED' or context._reprice_attempted:
            raise ValueError("ticket-change context is not ready for repricing")
        expected = (
            context.source_fingerprint, context.target_fingerprint,
        ) + _ticket_change_quote_tuple(context._quote)
        actual = (
            approval.source_fingerprint, approval.target_fingerprint,
            approval.original_amount, approval.new_amount,
            approval.additional_charge, approval.refund_amount,
        )
        if actual != expected:
            raise ValueError("ticket-change approval does not match the quote")
        context._approved_snapshot = expected
        try:
            if not isinstance(context._request, _TicketChangeRequest):
                raise ValueError("ticket-change request snapshot was replaced")
            data = context._request.to_dict(context._request_digest)
        except ValueError:
            context.state = 'REQUEST_TAMPERED'
            raise ValueError("ticket-change request snapshot was modified")
        data['prcFareReCalcFlg'] = 'Y'
        data['tmpJobSqno'] = context._temporary_pnr
        context._reprice_attempted = True
        context.state = 'REPRICING'
        response = self._ticket_change_post(
            KORAIL_TICKET_CHANGE_RESERVATION,
            data,
            context=context,
            mutation=True,
        )
        response_pnr = _get_utf8(response, 'h_pnr_no')
        if (not isinstance(response_pnr, str) or not response_pnr.strip() or
                response_pnr != context._temporary_pnr):
            self._ticket_change_ambiguous(context)
        try:
            context._lump_settlement_target = _ticket_change_lump_target(response)
        except KorailError:
            self._ticket_change_ambiguous(context)
        try:
            quote = _ticket_change_quote(response)
        except _TicketChangeMalformedResponse:
            self._ticket_change_ambiguous(context)
        except KorailError as error:
            context.state = 'REPRICE_MISMATCH'
            error.context = context
            raise
        if (quote.original_amount, quote.new_amount,
                quote.additional_charge, quote.refund_amount) != expected[2:]:
            context.state = 'REPRICE_MISMATCH'
            error = KorailError(
                "ticket-change fare changed during repricing", None)
            error.context = context
            raise error
        context._quote = quote
        payment_flag = _get_utf8(response, 'h_payment_flg')
        if payment_flag not in ('N', 'Y'):
            context.state = 'REPRICE_MISMATCH'
            error = KorailError(
                "ticket-change response has invalid payment flag", None)
            error.context = context
            raise error
        context._payment_flag = payment_flag
        context._pre_settlement_flag = _get_utf8(
            response, 'h_pre_stl_tgt_flg')
        context.state = 'REPRICED'
        return context

    def settle_ticket_change(self, context, card_config=None):
        """Settle a repriced change exactly once through IntgStl."""
        if not isinstance(context, TicketChangeContext):
            raise TypeError("context must be a TicketChangeContext")
        if context.state != 'REPRICED' or context._settle_attempted:
            raise ValueError("ticket-change context is not ready for settlement")
        current_snapshot = (
            context.source_fingerprint, context.target_fingerprint,
        ) + _ticket_change_quote_tuple(context._quote)
        if current_snapshot != context._approved_snapshot:
            context.state = 'QUOTE_TAMPERED'
            raise ValueError("ticket-change approved quote was modified")
        amount = context._quote.additional_charge
        if context._payment_flag != 'N':
            if card_config is not None:
                raise ValueError("card_config must be omitted for a pre-settled change")
            context._settle_attempted = True
            context.state = 'SUBMITTED_UNVERIFIED'
            result = TicketChangeResult(
                context.source_fingerprint, context.target_fingerprint,
                context._quote, 'SUBMITTED_UNVERIFIED', False,
                context._payment_flag,
                context._pre_settlement_flag,
            )
            return result
        if amount > 0 and card_config is None:
            raise ValueError("card_config is required for an additional charge")
        if amount == 0 and card_config is not None:
            raise ValueError("card_config must be omitted when there is no charge")
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'ctlDvCd': '3582',
            'stlPrsJobId': '0001',
            'cart_LumpStlTgtNo': context._lump_settlement_target,
        }
        if amount > 0:
            payment_context = PaymentContext(
                'ticket-change', 'ticket-change', 'ticket-change', '',
                'ticket-change', amount,
            )
            card_data = _build_card_payment_payload(
                payment_context, card_config,
            )
            for key in (
                    'hidPnrNo', 'hidWctNo', 'hidTmpJobSqno1',
                    'hidTmpJobSqno2', 'hidRsvChgNo', 'hiduserYn'):
                card_data.pop(key, None)
            data.update(card_data)
        context._settle_attempted = True
        context.state = 'SETTLING'
        self._ticket_change_post(
            KORAIL_TICKET_CHANGE_SETTLEMENT,
            data,
            context=context,
            mutation=True,
        )
        context.state = 'SUBMITTED_UNVERIFIED'
        result = TicketChangeResult(
            context.source_fingerprint, context.target_fingerprint,
            context._quote, 'SUBMITTED_UNVERIFIED', True,
            context._payment_flag,
            context._pre_settlement_flag,
        )
        result.settlement_submitted = True
        result.card_charge_submitted = amount > 0
        return result

    def rollback_ticket_change(self, context):
        """Explicitly discard a known temporary change exactly once."""
        if not isinstance(context, TicketChangeContext):
            raise TypeError("context must be a TicketChangeContext")
        if context.state not in ('PREPARED', 'REPRICED', 'PREPARE_MISMATCH',
                                  'REPRICE_MISMATCH', 'EXPLICIT_FAILURE',
                                  'QUOTE_TAMPERED', 'REQUEST_TAMPERED'):
            raise ValueError("ticket-change context cannot be rolled back safely")
        if context._rollback_attempted:
            raise ValueError("ticket-change rollback was already attempted")
        if not context._lump_settlement_target:
            raise ValueError("ticket-change context has no rollback target")
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'lumpStlCnt': '1',
            'lumpStlTgtNo_1': context._lump_settlement_target,
        }
        context._rollback_attempted = True
        context.state = 'ROLLING_BACK'
        self._ticket_change_post(
            KORAIL_TICKET_CHANGE_ROLLBACK,
            data,
            context=context,
            mutation=True,
        )
        context.state = 'ROLLED_BACK'
        return True

    def tickets(self):
        """Get list of tickets"""
        url = KORAIL_MYTICKETLIST
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'txtIndex': '1',
            'h_page_no': '1',
            'txtDeviceId': '',
            'h_abrd_dt_from': '',
            'h_abrd_dt_to': '',
        }

        r = self._session.get(url, params=data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        try:
            if self._result_check(j):
                ticket_infos = j['reservation_list']

                tickets = []

                for info in ticket_infos:
                    ticket = Ticket(info)
                    url = KORAIL_MYTICKET_SEAT
                    data = {
                        'Device': self._device,
                        'Version': self._version,
                        'Key': self._key,
                        'h_orgtk_wct_no': ticket.sale_info1,
                        'h_orgtk_ret_sale_dt': ticket.sale_info2,
                        'h_orgtk_sale_sqno': ticket.sale_info3,
                        'h_orgtk_ret_pwd': ticket.sale_info4,
                    }
                    r = self._session.get(url, params=data, timeout=REQUEST_TIMEOUT)
                    j = json.loads(r.text)
                    if self._result_check(j):
                        seat = j['ticket_infos']['ticket_info'][0]['tk_seat_info'][0]
                        ticket.seat_no = _get_utf8(seat, 'h_seat_no')
                        ticket.seat_no_end = None

                    tickets.append(ticket)

                return tickets
        except NoResultsError:
            return []

    def reservations(self):
        """ Get My Reservations """
        url = KORAIL_MYRESERVATIONLIST
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
        }
        r = self._session.get(url, params=data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        try:
            if self._result_check(j):
                rsv_infos = j['jrny_infos']['jrny_info']

                reserves = []

                for info in rsv_infos:
                    for tinfo in info['train_infos']['train_info']:
                        reserves.append(Reservation(tinfo))
                return reserves
        except NoResultsError:
            return []

    def cancel(self, rsv):
        """ Cancel Reservation : Canceling is for reservation, for ticket would be Refunding """
        assert isinstance(rsv, Reservation)
        url = KORAIL_CANCEL
        data = {
            'Device': self._device,
            'Version': self._version,
            'Key': self._key,
            'txtPnrNo': rsv.rsv_id,
            'txtJrnySqno': rsv.journey_no,
            'txtJrnyCnt': rsv.journey_cnt,
            'hidRsvChgNo': rsv.rsv_chg_no,
        }
        r = self._session.get(url, data=data, timeout=REQUEST_TIMEOUT)
        j = json.loads(r.text)
        if self._result_check(j):
            return True
