"""统计计算模块（已修复）。

修复记录：
- bug 1: average() 原除以 len(values)-1，已改为除以 len(values)
- bug 2: median() 偶数长度原返回 ordered[mid]，已改为取中间两数均值
"""


def average(values):
    """返回列表的算术平均值。"""
    if not values:
        raise ValueError("empty list")
    return sum(values) / len(values)


def median(values):
    """返回列表的中位数。"""
    if not values:
        raise ValueError("empty list")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) / 2
    return ordered[mid]


def main():
    data = [1.0, 2.0, 3.0, 4.0]
    print(f"average={average(data)} (期望 2.5)")
    print(f"median={median(data)} (期望 2.5)")


if __name__ == "__main__":
    main()
