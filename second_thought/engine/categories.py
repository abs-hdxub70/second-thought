"""Category normalisation, essentials, channel tags and service groups.

Everything here is plain lookup tables so it is easy to explain and to test.
"""

from __future__ import annotations

from ..models import Transaction

# Alipay exports its own category column (交易分类). Map it to our categories.
ALIPAY_CATEGORY_MAP = {
    "餐饮美食": "food",
    "超市便利": "groceries",
    "日用百货": "household",
    "服饰装扮": "clothing",
    "美容美发": "beauty",
    "数码电器": "electronics",
    "交通出行": "transport",
    "充值缴费": "utilities",
    "住房物业": "housing",
    "文化休闲": "entertainment",
    "教育培训": "education",
    "医疗健康": "health",
    "酒店旅游": "travel",
    "生活服务": "services",
    "运动户外": "sports",
    "转账红包": "transfer",
    "投资理财": "investment",
    "信用借还": "credit_repayment",
    "退款": "refund",
    "其他": "other",
}

# Merchant / description keywords (Chinese and English) -> category.
# Order matters: first match wins.
KEYWORD_CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("credit_repayment", ("花呗还款", "白条还款", "信用卡还款", "credit card payment")),
    ("fees", ("滞纳金", "逾期", "违约金", "late fee", "overdraft", "returned payment fee")),
    ("gambling", ("彩票", "lottery", "casino", "betting", "bet365")),
    ("subscriptions", (
        "会员", "vip", "自动续费", "连续包月", "订阅", "subscription", "premium",
        "spotify", "netflix", "icloud", "adobe", "百度网盘", "qq音乐", "网易云音乐",
        "爱奇艺", "腾讯视频", "优酷", "喜马拉雅", "哔哩哔哩大会员",
    )),
    ("food", ("美团", "饿了么", "外卖", "瑞幸", "喜茶", "星巴克", "starbucks", "麦当劳", "肯德基", "零食", "restaurant", "cafe", "snack")),
    ("household", ("收纳", "香薰", "床品", "绿植", "四件套", "candle", "storage box")),
    ("groceries", ("盒马", "超市", "便利店", "7-eleven", "全家", "美宜佳", "沃尔玛", "rewe", "edeka", "lidl", "aldi", "grocery")),
    ("transport", ("滴滴", "深圳通", "地铁", "高铁", "12306", "uber", "mvg", "deutsche bahn", "shell", "加油")),
    ("health", ("药房", "药店", "医院", "pharmacy", "apotheke", "clinic", "大参林", "老百姓大药房")),
    ("utilities", ("供电", "水务", "燃气", "中国移动", "中国联通", "中国电信", "电费", "话费", "vodafone", "telekom")),
    ("housing", ("房租", "自如", "链家", "物业", "rent")),
    ("beauty", ("美妆", "化妆", "口红", "精华", "面膜", "sephora", "丝芙兰", "lipstick", "lippenstift", "mascara", "skincare", "serum")),
    ("electronics", ("耳机", "手机", "平板", "数码", "apple store", "华为", "小米", "电脑", "earbuds", "headphones", "kopfhörer", "laptop", "smartphone", "tablet")),
    ("clothing", ("服饰", "外套", "夹克", "卫衣", "连衣裙", "大衣", "鞋", "优衣库", "zara", "h&m", "jacket", "coat", "hoodie", "sneaker", "jacke", "mantel", "kleid", "schuhe")),
    ("gaming", ("steam", "游戏", "王者荣耀", "原神", "playstation", "nintendo", "loot")),
    ("education", ("课程", "学费", "培训", "course", "tuition", "udemy", "coursera")),
    ("transfer", ("转账", "红包", "零钱通", "余额宝", "transfer")),
]

# Never held, never blocked: the agent must not get between someone and these.
ESSENTIAL_CATEGORIES = {"groceries", "health", "transport", "utilities", "housing", "education", "credit_repayment", "fees"}

# Purchases in these categories count as discretionary for insights.
DISCRETIONARY_CATEGORIES = {
    "food", "household", "clothing", "beauty", "electronics", "entertainment",
    "travel", "services", "sports", "gaming", "subscriptions", "gambling", "other",
}

# Categories where Chinese online purchases usually qualify for 7-day no-reason returns
# (Consumer Rights Protection Law, Art. 25 excludes custom, perishable, digital and print goods).
RETURNABLE_CATEGORIES = {"clothing", "beauty", "electronics", "household", "sports"}

LIVESTREAM_KEYWORDS = ("直播", "livestream", "live stream", "抖音商城", "抖音小店", "快手小店", "淘宝直播", "主播")
FLASH_SALE_KEYWORDS = ("秒杀", "限时", "flash sale", "倒计时", "抢购", "doorbuster")
ONLINE_KEYWORDS = ("淘宝", "天猫", "京东", "拼多多", "抖音", "快手", "唯品会", "amazon", "zalando", "online", "网购")
INSTALMENT_KEYWORDS = ("花呗", "白条", "分期", "klarna", "afterpay", "paypal pay in", "instal")

# Merchant category codes (ISO 18245) used for card / bank feeds.
MCC_CATEGORIES = {
    "5411": "groceries",
    "5812": "food",
    "5814": "food",
    "5912": "health",
    "4111": "transport",
    "4121": "transport",
    "4900": "utilities",
    "4814": "utilities",
    "5651": "clothing",
    "5691": "clothing",
    "5732": "electronics",
    "5977": "beauty",
    "5815": "subscriptions",
    "5817": "subscriptions",
    "5818": "subscriptions",
    "7995": "gambling",
    "5816": "gaming",
    "6513": "housing",
    "8220": "education",
}

# Plaid personal_finance_category.primary -> our category
PLAID_CATEGORY_MAP = {
    "FOOD_AND_DRINK": "food",
    "GENERAL_MERCHANDISE": "other",
    "TRANSPORTATION": "transport",
    "TRAVEL": "travel",
    "RENT_AND_UTILITIES": "utilities",
    "MEDICAL": "health",
    "PERSONAL_CARE": "beauty",
    "ENTERTAINMENT": "entertainment",
    "GENERAL_SERVICES": "services",
    "BANK_FEES": "fees",
    "LOAN_PAYMENTS": "credit_repayment",
    "TRANSFER_IN": "transfer",
    "TRANSFER_OUT": "transfer",
    "INCOME": "income",
    "HOME_IMPROVEMENT": "household",
    "GOVERNMENT_AND_NON_PROFIT": "other",
}

# Services that do the same job; two active ones in a group get flagged.
SERVICE_GROUPS = {
    "video": ("爱奇艺", "腾讯视频", "优酷", "芒果tv", "netflix", "disney", "哔哩哔哩大会员", "prime video"),
    "music": ("qq音乐", "网易云音乐", "spotify", "apple music", "酷狗"),
    "cloud": ("百度网盘", "icloud", "google one", "dropbox", "阿里云盘"),
    "audio": ("喜马拉雅", "audible", "得到"),
    "design": ("adobe", "canva", "figma"),
}


def _contains(text: str, words: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(w.lower() in t for w in words)


def service_group(merchant: str, description: str = "") -> str | None:
    text = f"{merchant} {description}"
    for group, names in SERVICE_GROUPS.items():
        if _contains(text, names):
            return group
    return None


def categorize(txn: Transaction) -> str:
    """Pick a category: explicit keywords first, then the provider's own label, then MCC."""
    text = f"{txn.merchant} {txn.description} {txn.payment_method}"
    for category, words in KEYWORD_CATEGORIES:
        if _contains(text, words):
            # A purchase *paid with* Huabei is not a repayment; only match repayment in merchant/description.
            if category == "credit_repayment" and not _contains(f"{txn.merchant} {txn.description}", words):
                continue
            return category
    if txn.raw_category in ALIPAY_CATEGORY_MAP:
        return ALIPAY_CATEGORY_MAP[txn.raw_category]
    if txn.raw_category in PLAID_CATEGORY_MAP:
        return PLAID_CATEGORY_MAP[txn.raw_category]
    if txn.mcc and txn.mcc in MCC_CATEGORIES:
        return MCC_CATEGORIES[txn.mcc]
    return "other"


def channel_tags(txn: Transaction) -> list[str]:
    text = f"{txn.merchant} {txn.description}"
    tags: list[str] = []
    if _contains(text, LIVESTREAM_KEYWORDS):
        tags.append("livestream")
    if _contains(text, FLASH_SALE_KEYWORDS):
        tags.append("flash_sale")
    if "livestream" in tags or _contains(text, ONLINE_KEYWORDS):
        tags.append("online")
    return tags


def detect_instalment(payment_method: str, description: str = "") -> tuple[bool, int]:
    """Return (is_instalment_or_bnpl, number_of_instalments or 0)."""
    text = f"{payment_method} {description}"
    if not _contains(text, INSTALMENT_KEYWORDS):
        return False, 0
    import re

    m = re.search(r"(\d+)\s*期", text) or re.search(r"(\d+)\s*(?:instalments|installments|x)", text, re.I)
    return True, int(m.group(1)) if m else 0


def enrich(txn: Transaction) -> Transaction:
    """Fill category, tags and instalment flags in place and return the transaction."""
    if txn.category in ("", "other"):
        txn.category = categorize(txn)
    for tag in channel_tags(txn):
        if tag not in txn.tags:
            txn.tags.append(tag)
    if txn.category == "fees" and "fee" not in txn.tags:
        txn.tags.append("fee")
    inst, count = detect_instalment(txn.payment_method, txn.description)
    if inst:
        txn.is_instalment = True
        txn.instalment_count = count
    return txn
