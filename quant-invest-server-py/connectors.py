# -*- coding: utf-8 -*-
"""账户连接器：为智能体连接真实账户预留的统一接口。

AccountConnector 定义 login / check_connection / fetch_balance / get_status 四个能力；
目前提供模拟盘连接器（资金固定 100 万）与通用 HTTP 连接器（链接连通性探测 + 登录探测占位）。
后续接入真实券商/交易平台时，新增 Connector 实现并在 get_connector 中路由即可，
凭证层（credentials.py）无需改动；智能体经连接器拿会话，而不是裸密码。
"""
import urllib.error
import urllib.request


class AccountConnector:
    """账户连接器基类。"""

    def login(self, url: str, login_account: str, password: str) -> dict:
        """登录目标平台，成功返回 {'ok': True, 'message': ...}（后续可扩展会话对象）。"""
        raise NotImplementedError

    def check_connection(self, url: str, login_account: str, password: str) -> dict:
        """检测账户连接：链接可达性 + 凭证完整性，返回 {'ok': bool, 'message': str}。"""
        raise NotImplementedError

    def fetch_balance(self, url: str, login_account: str, password: str) -> dict:
        """连接后读取账户资金，返回 {'ok': bool, 'totalAssets': float|None, 'cash': float|None, 'message': str}。"""
        return {'ok': False, 'totalAssets': None, 'cash': None, 'message': '资金读取待接入平台适配器'}

    def get_status(self, account_row: dict) -> str:
        """读取账户当前连通状态（untested / ok / fail）。"""
        return (account_row or {}).get('connect_status', 'untested')


class SimulatedConnector(AccountConnector):
    """模拟盘连接器：连接成功后账户资金固定为 1,000,000。"""

    SIM_BALANCE = 1000000.0

    def login(self, url: str, login_account: str, password: str) -> dict:
        return {'ok': True, 'message': '模拟盘无需真实登录'}

    def check_connection(self, url: str, login_account: str, password: str) -> dict:
        return {'ok': True, 'message': '模拟盘连接成功'}

    def fetch_balance(self, url: str, login_account: str, password: str) -> dict:
        return {
            'ok': True,
            'totalAssets': self.SIM_BALANCE,
            'cash': self.SIM_BALANCE,
            'message': '模拟盘账户资金 ¥1,000,000',
        }


class GenericHttpConnector(AccountConnector):
    """通用 HTTP 连接器：探测链接可达性，登录为占位实现。"""

    TIMEOUT = 8

    def login(self, url: str, login_account: str, password: str) -> dict:
        # 占位：真实平台登录需各自的适配器，这里仅校验凭证完整性
        if not (login_account and password):
            return {'ok': False, 'message': '缺少账号或密码，无法登录'}
        return {'ok': True, 'message': '通用连接器暂不模拟真实登录，请接入对应平台适配器'}

    def check_connection(self, url: str, login_account: str, password: str) -> dict:
        if not url:
            return {'ok': False, 'message': '未填写账户链接地址'}
        if not url.startswith(('http://', 'https://')):
            return {'ok': False, 'message': '链接地址需以 http(s):// 开头'}
        req = urllib.request.Request(url, headers={'User-Agent': 'iktsuarpok-connector/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            return {'ok': False, 'message': f'无法访问链接：{e}'}
        if code >= 500:
            return {'ok': False, 'message': f'链接返回 {code}'}
        return {'ok': True, 'message': f'链接可达（HTTP {code}），登录连通待接入平台适配器'}


def get_connector(account_type: str = '') -> AccountConnector:
    """按账户类型取连接器：模拟盘走模拟连接器，其余暂用通用 HTTP 连接器。"""
    if (account_type or '').startswith('模拟'):
        return SimulatedConnector()
    return GenericHttpConnector()
