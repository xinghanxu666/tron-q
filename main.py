from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import aiohttp
import json
import time
from typing import Optional

# 波场相关常量
TRON_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TRONGRID_API = "https://api.trongrid.io"

@register("tron_address", "YourName", "波场地址查询插件", "1.0.0")
class TronAddressPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.session = aiohttp.ClientSession()
        self.config = config
        # 从配置中获取TRONGRID API密钥
        self.trongrid_api_key = self.config.get('trongrid_api_key', '')
        logger.info(f"TronAddressPlugin 初始化完成，API密钥: {'已设置' if self.trongrid_api_key else '未设置'}")

    async def terminate(self):
        """关闭HTTP会话"""
        await self.session.close()
        logger.info("TronAddressPlugin 已关闭")

    async def fetch_tron_data(self, address: str) -> Optional[dict]:
        """获取波场地址数据"""
        try:
            # 获取账户基本信息
            url = f"{TRONGRID_API}/v1/accounts/{address}"
            headers = {}
            if self.trongrid_api_key:
                headers["TRON-PRO-API-KEY"] = self.trongrid_api_key
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    # 如果返回429错误，提示API密钥限制
                    if response.status == 429:
                        logger.warning("TRONGRID API请求受限，请配置API密钥")
                        return "rate_limit"
                    return None
                data = await response.json()
                return data.get("data", [{}])[0] if data.get("data") else {}
        except Exception as e:
            logger.error(f"获取波场数据出错: {str(e)}")
            return None

    async def get_usdt_balance(self, address: str) -> float:
        """获取USDT余额"""
        try:
            payload = {
                "contract_address": TRON_USDT_CONTRACT,
                "owner_address": address,
                "function_selector": "balanceOf(address)",
                "parameter": f"000000000000000000000000{address[1:]}"
            }
            url = f"{TRONGRID_API}/wallet/triggerconstantcontract"
            headers = {}
            if self.trongrid_api_key:
                headers["TRON-PRO-API-KEY"] = self.trongrid_api_key
            async with self.session.post(url, json=payload, headers=headers) as response:
                data = await response.json()
                if "constant_result" in data:
                    # 解析余额 (USDT有6位小数)
                    hex_balance = data["constant_result"][0]
                    balance = int(hex_balance, 16) / 10**6
                    return balance
            return 0.0
        except Exception as e:
            logger.error(f"获取USDT余额出错: {str(e)}")
            return 0.0

    def format_timestamp(self, ts: int) -> str:
        """格式化时间戳"""
        if not ts:
            return "未激活"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts/1000))

    @filter.command("tron")
    async def tron_address_info(self, event: AstrMessageEvent, address: str):
        """查询波场地址信息"""
        # 验证地址格式
        if not address.startswith("T") or len(address) != 34:
            yield event.plain_result("⚠️ 地址格式错误，请输入有效的波场地址（以T开头，34位字符）")
            return
        
        # 检查API密钥是否配置
        if not self.trongrid_api_key:
            yield event.plain_result("⚠️ 请先在插件配置中设置TRONGRID API密钥")
            return
        
        # 显示查询中消息
        yield event.plain_result(f"🔍 正在查询地址 {address}，请稍候...")
        
        # 获取数据
        data = await self.fetch_tron_data(address)
        
        # 处理API限制情况
        if data == "rate_limit":
            yield event.plain_result("⚠️ API请求受限，请检查您的TRONGRID API密钥或稍后重试")
            return
        elif not data:
            yield event.plain_result("❌ 获取地址信息失败，请检查地址或稍后重试")
            return
        
        # 获取USDT余额
        usdt_balance = await self.get_usdt_balance(address)
        
        # 提取所需信息
        trx_balance = data.get("balance", 0) / 10**6
        create_time = self.format_timestamp(data.get("create_time"))
        transaction_count = data.get("transaction_count", 0)
        
        # 带宽和能量信息
        bandwidth = data.get("free_net_usage", 0)
        bandwidth_limit = data.get("free_net_limit", 0)
        energy_usage = data.get("account_resource", {}).get("energy_usage", 0)
        energy_limit = data.get("account_resource", {}).get("energy_limit", 0)
        
        # 投票信息
        votes = data.get("votes", [])
        vote_info = "无投票" if not votes else f"已投票给 {len(votes)} 个代表"
        
        # 构建回复消息
        result = (
            f"🔷 波场地址: {address}\n"
            f"💰 TRX 余额: {trx_balance:.2f} TRX\n"
            f"💵 USDT 余额: {usdt_balance:.2f} USDT\n"
            f"⏱️ 激活时间: {create_time}\n"
            f"🔄 交易次数: {transaction_count}\n"
            f"📶 带宽: {bandwidth}/{bandwidth_limit}\n"
            f"⚡ 能量: {energy_usage}/{energy_limit}\n"
            f"🗳️ 投票情况: {vote_info}"
        )
        
        yield event.plain_result(result)

    @filter.command("tron.help")
    async def tron_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = (
            "📝 波场地址查询插件使用说明:\n"
            "命令格式: /tron [波场地址]\n"
            "示例: /tron TYmc3r6uVohbWg7VbJp8JzKX2uL5aM3s4B\n\n"
            "查询内容包含:\n"
            "- TRX 和 USDT 余额\n"
            "- 账户激活时间\n"
            "- 交易次数\n"
            "- 带宽和能量使用情况\n"
            "- 投票信息\n\n"
            "⚠️ 使用前请确保在插件配置中设置TRONGRID API密钥"
        )
        yield event.plain_result(help_text)
