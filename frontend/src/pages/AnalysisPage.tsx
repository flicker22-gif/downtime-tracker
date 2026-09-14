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
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { api } from "../api";
import ParetoChart, { vitalCount } from "../components/ParetoChart";
import { Line, ParetoItem } from "../types";

const { Title, Text } = Typography;

type RangeKey = "7" | "30" | "90" | "all";

export default function AnalysisPage() {
  const [lines, setLines] = useState<Line[]>([]);
  const [rangeKey, setRangeKey] = useState<RangeKey>("30");
  const [lineId, setLineId] = useState<number | undefined>();
  const [data, setData] = useState<ParetoItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalDuration, setTotalDuration] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listLines().then(setLines).catch(() => undefined);
  }, []);

  const period = useMemo(() => {
    if (rangeKey === "all") return undefined;
    const days = Number(rangeKey);
    return {
      from: dayjs().subtract(days, "day").toISOString(),
      to: dayjs().toISOString(),
    };
  }, [rangeKey]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.pareto({
        date_from: period?.from,
        date_to: period?.to,
        line_id: lineId,
        top: 10,
      });
      setData(res.items);
      setTotalCount(res.total_count);
      setTotalDuration(res.total_duration_min);
    } catch {
      message.error("加载分析数据失败");
    } finally {
      setLoading(false);
    }
  }, [period, lineId]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<ParetoItem> = [
    { title: "排名", width: 70, align: "center", render: (_, __, i) => i + 1 },
    {
      title: "原因大类",
      dataIndex: "category",
      width: 120,
      render: (v: string) => <Tag bordered={false}>{v}</Tag>,
    },
    { title: "停机原因", dataIndex: "reason_name" },
    {
      title: "次数",
      dataIndex: "count",
      width: 90,
      align: "right",
      sorter: (a, b) => a.count - b.count,
    },
    {
      title: "次数占比",
      dataIndex: "count_pct",
      width: 100,
      align: "right",
      render: (v: number) => `${v}%`,
    },
    {
      title: "累计占比",
      dataIndex: "cum_pct",
      width: 100,
      align: "right",
      render: (v: number) => <Text strong>{v}%</Text>,
    },
    {
      title: "停机时长(分)",
      dataIndex: "duration_min",
      width: 120,
      align: "right",
      sorter: (a, b) => a.duration_min - b.duration_min,
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        停机原因分析（帕累托）
      </Title>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
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
        <Col span={8}>
          <Card size="small">
            <Statistic title="停机总次数" value={totalCount} suffix="次" />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="停机总时长"
              value={totalDuration}
              suffix="分钟"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="关键原因（至累计 80%）"
              value={vitalCount(data)}
              suffix="项"
            />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title="原因排序（蓝条为关键少数，至累计占比首次达到 80%）"
        style={{ marginBottom: 12 }}
        loading={loading}
      >
        <ParetoChart items={data} />
      </Card>

      <Card size="small" title="明细表">
        <Table
          rowKey="reason_id"
          size="small"
          columns={columns}
          dataSource={data}
          pagination={false}
          footer={() => (
            <Text type="secondary">
              排序规则：按停机次数降序；累计占比用于识别「关键少数」原因，优先安排改善。
            </Text>
          )}
        />
      </Card>
    </div>
  );
}
