import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { api, EventQuery } from "../api";
import EventCreateModal from "../components/EventCreateModal";
import {
  EventListItem,
  EventStatus,
  Line,
  Reason,
  STATUS_META,
} from "../types";

const { RangePicker } = DatePicker;
const { Title } = Typography;

interface FilterValues {
  line_id?: number;
  reason_id?: number;
  status?: EventStatus;
  range?: [dayjs.Dayjs, dayjs.Dayjs];
  keyword?: string;
}

export default function EventListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<EventListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState<FilterValues>({});

  const [lines, setLines] = useState<Line[]>([]);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q: EventQuery = {
        page,
        page_size: pageSize,
        line_id: filters.line_id,
        reason_id: filters.reason_id,
        status: filters.status,
        q: filters.keyword?.trim() || undefined,
        date_from: filters.range?.[0]?.toISOString(),
        date_to: filters.range?.[1]?.toISOString(),
      };
      const res = await api.listEvents(q);
      setData(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载事件列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.listLines().then(setLines).catch(() => undefined);
    api.listReasons().then(setReasons).catch(() => undefined);
  }, []);

  const columns: ColumnsType<EventListItem> = [
    {
      title: "事件编号",
      dataIndex: "event_no",
      width: 150,
      fixed: "left",
      render: (v: string, r) => (
        <a onClick={() => navigate(`/events/${r.id}`)}>{v}</a>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 110,
      render: (s: EventStatus) => (
        <Tag color={STATUS_META[s].color}>{STATUS_META[s].label}</Tag>
      ),
    },
    { title: "产线", dataIndex: "line_name", width: 120 },
    { title: "设备", dataIndex: "equipment_name", width: 130 },
    {
      title: "停机原因",
      dataIndex: "reason_name",
      width: 150,
      render: (v: string, r) => (
        <Space size={4}>
          <Tag bordered={false}>{r.reason_category}</Tag>
          {v}
        </Space>
      ),
    },
    {
      title: "开始时间",
      dataIndex: "start_time",
      width: 170,
      render: (v: string) => dayjs(v).format("MM-DD HH:mm"),
    },
    {
      title: "时长(分)",
      dataIndex: "duration_min",
      width: 90,
      align: "right",
      render: (v?: number | null) => v ?? "—",
    },
    { title: "班次", dataIndex: "shift", width: 70 },
    { title: "操作工", dataIndex: "reporter", width: 90 },
    { title: "工单/产品", dataIndex: "product", width: 110, render: (v) => v ?? "—" },
    {
      title: "分析",
      dataIndex: "has_analysis",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="blue">已分析</Tag> : <Tag>待分析</Tag>,
    },
    {
      title: "未闭环措施",
      dataIndex: "open_actions",
      width: 100,
      align: "center",
      render: (n: number) =>
        n > 0 ? <Tag color="orange">{n} 项</Tag> : "—",
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginTop: 0 }}>
        停机事件
      </Title>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Form
          layout="inline"
          onFinish={(values: FilterValues) => {
            setPage(1);
            setFilters(values);
          }}
          initialValues={filters}
        >
          <Form.Item name="line_id" label="产线">
            <Select
              allowClear
              placeholder="全部"
              style={{ width: 150 }}
              options={lines.map((l) => ({ value: l.id, label: l.name }))}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              allowClear
              placeholder="全部"
              style={{ width: 130 }}
              options={(
                Object.keys(STATUS_META) as EventStatus[]
              ).map((k) => ({ value: k, label: STATUS_META[k].label }))}
            />
          </Form.Item>
          <Form.Item name="range" label="停机日期">
            <RangePicker showTime />
          </Form.Item>
          <Form.Item name="keyword" label="关键字">
            <Input allowClear placeholder="编号/操作工/设备/工单" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                查询
              </Button>
              <Button
                onClick={() => {
                  setFilters({});
                  setPage(1);
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card
        size="small"
        title={`共 ${total} 条`}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              登记停机
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <EventCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={load}
        lines={lines}
        reasons={reasons}
      />
    </div>
  );
}
