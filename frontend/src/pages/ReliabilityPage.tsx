import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { api } from "../api";
import { Line, ReliabilityRow } from "../types";

const { Title, Text } = Typography;

type RangeKey = "7" | "30" | "90" | "all";

/** 分钟数格式化成「x小时y分」 */
function fmtMinutes(min: number | null | undefined): string {
  if (min == null) return "—";
  if (min < 60) return `${round1(min)} 分`;
  const h = Math.floor(min / 60);
  const m = round1(min % 60);
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
}

function round1(v: number) {
  return Math.round(v * 10) / 10;
}

function availColor(pct: number | null): string {
  if (pct == null) return "#d9d9d9";
  if (pct >= 95) return "#0ca30c";
  if (pct >= 90) return "#2a78d6";
  if (pct >= 80) return "#eda100";
  return "#d03b3b";
}

export default function ReliabilityPage() {
  const [lines, setLines] = useState<Line[]>([]);
  const [dimension, setDimension] = useState<"equipment" | "line">("equipment");
  const [rangeKey, setRangeKey] = useState<RangeKey>("30");
  const [lineId, setLineId] = useState<number | undefined>();
  const [rows, setRows] = useState<ReliabilityRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listLines().then(setLines).catch(() => undefined);
  }, []);

  const period = useMemo<{ from?: string; to: string; allData: boolean }>(() => {
    const to = dayjs().toISOString();
    if (rangeKey === "all") {
      return { to, allData: true };
    }
    return { from: dayjs().subtract(Number(rangeKey), "day").toISOString(), to, allData: false };
  }, [rangeKey]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.reliability({
        dimension,
        line_id: lineId,
        date_from: period.from,
        date_to: period.to,
        all_data: period.allData,
      });
      setRows(res.rows);
    } catch {
      message.error("加载可靠性指标失败");
    } finally {
      setLoading(false);
    }
  }, [dimension, lineId, period]);

  useEffect(() => {
    load();
  }, [load]);

  const totals = useMemo(() => {
    const failures = rows.reduce((s, r) => s + r.failure_count, 0);
    const downtime = rows.reduce((s, r) => s + r.failure_downtime_min, 0);
    const observation = rows.reduce((s, r) => s + r.observation_min, 0);
    return {
      failures,
      downtime,
      mttr: failures ? downtime / failures : null,
      availability: observation ? (observation - downtime) / observation * 100 : null,
    };
  }, [rows]);

  const columns: ColumnsType<ReliabilityRow> = [
    {
      title: dimension === "equipment" ? "设备" : "产线",
      dataIndex: "name",
      width: 200,
      render: (v: string, r) => (
        <Space size={6}>
          <Text type="secondary">{r.code}</Text>
          <Text strong>{v}</Text>
        </Space>
      ),
    },
    ...(dimension === "equipment"
      ? [
          {
            title: "所属产线",
            dataIndex: "line_name",
            width: 130,
            render: (v: string | null) => v ?? "—",
          } as ColumnsType<ReliabilityRow>[number],
        ]
      : [
          {
            title: "设备数",
            dataIndex: "equipment_count",
            width: 90,
            align: "right" as const,
          },
        ]),
    {
      title: "故障次数",
      dataIndex: "failure_count",
      width: 100,
      align: "right",
      sorter: (a, b) => a.failure_count - b.failure_count,
      defaultSortOrder: "descend" as const,
      render: (n: number) => (n > 0 ? n : <Text type="secondary">0</Text>),
    },
    {
      title: "故障停机时长",
      dataIndex: "failure_downtime_min",
      width: 150,
      align: "right",
      sorter: (a, b) => a.failure_downtime_min - b.failure_downtime_min,
      render: (v: number) => fmtMinutes(v),
    },
    {
      title: () => (
        <Space size={4}>
          MTTR（平均修复）
          <Tooltip title="MTTR = 故障停机总时长 ÷ 故障次数，越小说明修复越快">
            <InfoCircleOutlined style={{ color: "#898781" }} />
          </Tooltip>
        </Space>
      ),
      dataIndex: "mttr_min",
      width: 150,
      align: "right",
      sorter: (a, b) => (a.mttr_min ?? -1) - (b.mttr_min ?? -1),
      render: (v: number | null) =>
        v == null ? <Tag>无故障</Tag> : <Text strong>{fmtMinutes(v)}</Text>,
    },
    {
      title: () => (
        <Space size={4}>
          MTBF（平均无故障）
          <Tooltip title="MTBF =（运行时长基数 − 故障停机时长）÷ 故障次数，越大越可靠；产线维度的运行时长基数按产线内设备数叠加">
            <InfoCircleOutlined style={{ color: "#898781" }} />
          </Tooltip>
        </Space>
      ),
      dataIndex: "mtbf_min",
      width: 170,
      align: "right",
      sorter: (a, b) => (a.mtbf_min ?? Infinity) - (b.mtbf_min ?? Infinity),
      render: (v: number | null) =>
        v == null ? <Tag color="success">无故障</Tag> : fmtMinutes(v),
    },
    {
      title: "可用度",
      dataIndex: "availability_pct",
      width: 180,
      align: "right",
      sorter: (a, b) => (a.availability_pct ?? 100) - (b.availability_pct ?? 100),
      render: (pct: number | null) => {
        const v = pct ?? 100;
        return (
          <Space size={8} style={{ justifyContent: "flex-end", width: "100%" }}>
            <div
              style={{
                width: 80,
                height: 8,
                borderRadius: 4,
                background: "#f0f0f0",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.max(0, Math.min(100, v))}%`,
                  height: "100%",
                  background: availColor(v),
                }}
              />
            </div>
            <Text style={{ minWidth: 52, textAlign: "right" }}>{round1(v)}%</Text>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        设备可靠性（MTTR / MTBF）
      </Title>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Segmented
            value={dimension}
            onChange={(v) => setDimension(v as "equipment" | "line")}
            options={[
              { label: "按设备", value: "equipment" },
              { label: "按产线", value: "line" },
            ]}
          />
          <Segmented
            value={rangeKey}
            onChange={(v) => setRangeKey(v as RangeKey)}
            options={[
              { label: "近 7 天", value: "7" },
              { label: "近 30 天", value: "30" },
              { label: "近 90 天", value: "90" },
              { label: "全部", value: "all" },
            ]}
          />
          <Select
            allowClear
            placeholder="全部产线"
            style={{ width: 160 }}
            value={lineId}
            onChange={setLineId}
            options={lines.map((l) => ({ value: l.id, label: l.name }))}
          />
          <Button onClick={load}>刷新</Button>
        </Space>
      </Card>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="故障总次数" value={totals.failures} suffix="次" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="故障总停机"
              value={totals.downtime >= 60 ? round1(totals.downtime / 60) : totals.downtime}
              suffix={totals.downtime >= 60 ? "小时" : "分钟"}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="整体 MTTR"
              value={totals.mttr == null ? "—" : fmtMinutes(totals.mttr)}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="整体可用度"
              value={totals.availability == null ? "—" : `${round1(totals.availability)}%`}
              valueStyle={{
                color: totals.availability == null ? undefined : availColor(totals.availability),
              }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title={
          dimension === "equipment"
            ? "各设备可靠性指标（默认按故障次数降序）"
            : "各产线可靠性指标（运行时长按产线内设备数叠加）"
        }
      >
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
          footer={() => (
            <Text type="secondary">
              口径：仅统计「设备故障」类原因（机械/电气/刀具模具）导致的停机；
              换型、待料、质量等不计为故障。MTBF =（运行时长基数 − 故障停机时长）÷ 故障次数，
              运行时长基数取所选区间、设备按 7×24 折算（产线按设备数叠加）；
              「全部」时观察起点取最早停机事件时间。无故障设备不显示 MTTR/MTBF，可用度 100%。
            </Text>
          )}
        />
      </Card>
    </div>
  );
}
