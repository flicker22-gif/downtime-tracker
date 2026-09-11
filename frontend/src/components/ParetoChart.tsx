import { Tooltip } from "antd";
import type { ParetoItem } from "../types";

/**
 * 单轴帕累托图：
 * - 横向条长度 = 停机次数（唯一数值轴）
 * - 条右侧标注该原因的累计占比 %
 * - 累计 ≤ 80% 的原因着蓝色（关键少数），之后为中性灰（次要多数）
 * 不使用双 Y 轴；时长信息在 Tooltip 与明细表中展示。
 */
export default function ParetoChart({ items }: { items: ParetoItem[] }) {
  const maxCount = Math.max(1, ...items.map((i) => i.count));

  if (items.length === 0) {
    return (
      <div style={{ color: "#898781", padding: "24px 0", textAlign: "center" }}>
        当前筛选条件下暂无数据
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        paddingTop: 4,
      }}
    >
      {items.map((it) => {
        const vital = it.cum_pct - it.count_pct < 80 || it.cum_pct <= 80;
        const widthPct = Math.max(2, (it.count / maxCount) * 100);
        return (
          <div
            key={it.reason_id}
            style={{ display: "flex", alignItems: "center", gap: 10 }}
          >
            <div
              style={{
                width: 170,
                flex: "0 0 170px",
                textAlign: "right",
                color: "#52514e",
                fontSize: 13,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={`${it.category} / ${it.reason_name}`}
            >
              {it.reason_name}
            </div>
            <Tooltip
              title={
                <div>
                  <div>
                    {it.category} / {it.reason_name}
                  </div>
                  <div>停机次数：{it.count} 次（{it.count_pct}%）</div>
                  <div>累计占比：{it.cum_pct}%</div>
                  <div>停机时长：{it.duration_min} 分钟</div>
                </div>
              }
            >
              <div style={{ flex: 1, position: "relative", height: 22 }}>
                <div
                  style={{
                    width: `${widthPct}%`,
                    height: "100%",
                    minWidth: 4,
                    background: vital ? "#2a78d6" : "#86b6ef",
                    borderRadius: 4,
                    transition: "width .3s ease",
                  }}
                />
              </div>
            </Tooltip>
            <div
              style={{
                width: 110,
                flex: "0 0 110px",
                fontSize: 13,
                color: "#0b0b0b",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {it.count} 次 · 累计 {it.cum_pct}%
            </div>
          </div>
        );
      })}
    </div>
  );
}
