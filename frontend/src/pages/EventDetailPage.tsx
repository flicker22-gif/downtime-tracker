import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ArrowLeftOutlined, SaveOutlined, PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import {
  ACTION_STATUS_META,
  ActionStatus,
  CorrectiveAction,
  EventDetail,
  EventStatus,
  STATUS_META,
} from "../types";

const { Title, Paragraph, Text } = Typography;

type FiveWhyForm = {
  problem_statement: string;
  why1?: string;
  why2?: string;
  why3?: string;
  why4?: string;
  why5?: string;
  root_cause?: string;
  analyst: string;
};

const WHY_FIELDS: { name: keyof FiveWhyForm; label: string }[] = [
  { name: "why1", label: "Why 1 — 为什么会发生？" },
  { name: "why2", label: "Why 2 — 为什么？" },
  { name: "why3", label: "Why 3 — 为什么？" },
  { name: "why4", label: "Why 4 — 为什么？" },
  { name: "why5", label: "Why 5 — 根因层" },
];

export default function EventDetailPage() {
  const { id } = useParams();
  const eventId = Number(id);
  const navigate = useNavigate();

  const [event, setEvent] = useState<EventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FiveWhyForm>();
  const [analysisDirty, setAnalysisDirty] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getEvent(eventId);
      setEvent(data);
      if (data.analysis) {
        form.setFieldsValue({
          problem_statement: data.analysis.problem_statement,
          why1: data.analysis.why1 ?? "",
          why2: data.analysis.why2 ?? "",
          why3: data.analysis.why3 ?? "",
          why4: data.analysis.why4 ?? "",
          why5: data.analysis.why5 ?? "",
          root_cause: data.analysis.root_cause ?? "",
          analyst: data.analysis.analyst,
        });
      } else {
        form.resetFields();
      }
      setAnalysisDirty(false);
    } catch {
      message.error("加载事件失败");
    } finally {
      setLoading(false);
    }
  }, [eventId, form]);

  useEffect(() => {
    load();
  }, [load]);

  const saveAnalysis = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await api.saveAnalysis(eventId, {
        problem_statement: values.problem_statement.trim(),
        why1: values.why1?.trim() || null,
        why2: values.why2?.trim() || null,
        why3: values.why3?.trim() || null,
        why4: values.why4?.trim() || null,
        why5: values.why5?.trim() || null,
        root_cause: values.root_cause?.trim() || null,
        analyst: values.analyst.trim(),
      });
      message.success("5 Whys 已保存");
      await load();
    } catch (e: any) {
      if (e?.errorFields) return; // 表单校验失败
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (status: EventStatus) => {
    const updated = await api.updateEvent(eventId, { status });
    setEvent(updated);
    message.success("状态已更新");
  };

  if (loading || !event) {
    return <Card loading={loading} style={{ minHeight: 300 }} />;
  }

  const openActions = event.actions.filter((a) => a.status !== "done").length;

  const actionColumns: ColumnsType<CorrectiveAction> = [
    {
      title: "改善措施",
      dataIndex: "content",
      render: (v: string, r) =>
        r.status === "done" ? <Text delete>{v}</Text> : v,
    },
    { title: "责任人", dataIndex: "owner", width: 120 },
    {
      title: "计划完成",
      dataIndex: "due_date",
      width: 130,
      render: (v?: string | null) =>
        v ? (
          <Text type={dayjs(v).isBefore(dayjs()) ? "danger" : undefined}>
            {dayjs(v).format("YYYY-MM-DD")}
          </Text>
        ) : (
          "—"
        ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 150,
      render: (s: ActionStatus, r) => (
        <Select
          size="small"
          value={s}
          style={{ width: 110 }}
          onChange={async (val: ActionStatus) => {
            const updated = await api.updateAction(eventId, r.id, {
              status: val,
            });
            setEvent({ ...event, actions: event.actions.map((a) => (a.id === r.id ? updated : a)) });
          }}
          options={(Object.keys(ACTION_STATUS_META) as ActionStatus[]).map(
            (k) => ({ value: k, label: ACTION_STATUS_META[k].label })
          )}
        />
      ),
    },
    {
      title: "操作",
      width: 130,
      render: (_, r) => (
        <Space size="small">
          <ActionEditModal action={r} eventId={eventId} onSaved={load} />
          <Popconfirm
            title="删除该措施？"
            onConfirm={async () => {
              await api.deleteAction(eventId, r.id);
              message.success("已删除");
              load();
            }}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("/")}
        >
          返回列表
        </Button>
        <Title level={4} style={{ margin: 0 }}>
          {event.event_no}
        </Title>
        <Tag color={STATUS_META[event.status].color}>
          {STATUS_META[event.status].label}
        </Tag>
      </Space>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="停机时长(分钟)" value={event.duration_min ?? "—"} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="5 Whys" value={event.analysis ? "已完成" : "待分析"} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="改善措施" value={`${event.actions.length - openActions}/${event.actions.length}`} suffix="已完成" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="未闭环"
              value={openActions}
              valueStyle={{ color: openActions > 0 ? "#d46b08" : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="事件信息" style={{ marginBottom: 12 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="产线">{event.line_name}</Descriptions.Item>
          <Descriptions.Item label="设备">
            {event.equipment_name}
          </Descriptions.Item>
          <Descriptions.Item label="停机原因">
            <Space size={4}>
              <Tag bordered={false}>{event.reason_category}</Tag>
              {event.reason_name}
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="开始时间">
            {dayjs(event.start_time).format("YYYY-MM-DD HH:mm")}
          </Descriptions.Item>
          <Descriptions.Item label="结束时间">
            {event.end_time
              ? dayjs(event.end_time).format("YYYY-MM-DD HH:mm")
              : "进行中（后补）"}
          </Descriptions.Item>
          <Descriptions.Item label="班次">{event.shift}</Descriptions.Item>
          <Descriptions.Item label="操作工">{event.reporter}</Descriptions.Item>
          <Descriptions.Item label="工单/产品">
            {event.product ?? "—"}
          </Descriptions.Item>
          <Descriptions.Item label="登记时间">
            {dayjs(event.created_at).format("MM-DD HH:mm")}
          </Descriptions.Item>
          <Descriptions.Item label="现象备注" span={3}>
            {event.note ?? "—"}
          </Descriptions.Item>
        </Descriptions>
        <Space style={{ marginTop: 8 }}>
          {event.status === "open" && (
            <Button onClick={() => changeStatus("analyzing")}>
              开始分析
            </Button>
          )}
          {event.status === "analyzing" && (
            <Popconfirm
              title="确认关闭该事件？关闭前请确保措施已闭环"
              onConfirm={() => changeStatus("closed")}
            >
              <Button type="primary">关闭事件</Button>
            </Popconfirm>
          )}
          {event.status === "closed" && (
            <Button onClick={() => changeStatus("analyzing")}>
              重新打开
            </Button>
          )}
        </Space>
      </Card>

      <Card
        size="small"
        title="5 Whys 根因分析（班组长填写）"
        style={{ marginBottom: 12 }}
        extra={
          event.analysis && (
            <Text type="secondary">
              分析人：{event.analysis.analyst} · 更新于{" "}
              {dayjs(event.analysis.updated_at).format("MM-DD HH:mm")}
            </Text>
          )
        }
      >
        {event.status === "closed" && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="事件已关闭，仍可修订分析内容"
          />
        )}
        <Form
          form={form}
          layout="vertical"
          onValuesChange={() => setAnalysisDirty(true)}
        >
          <Form.Item
            label="问题描述（停机现象）"
            name="problem_statement"
            rules={[{ required: true, message: "请描述问题" }]}
          >
            <Input.TextArea rows={2} placeholder="例如：冲压机A在生产中突发停机，持续45分钟" />
          </Form.Item>
          {WHY_FIELDS.map((f, idx) => (
            <Row gutter={12} key={f.name} align="middle">
              <Col flex="auto">
                <Form.Item label={f.label} name={f.name} style={{ marginBottom: 10 }}>
                  <Input.TextArea
                    rows={1}
                    autoSize={{ minRows: 1, maxRows: 3 }}
                    placeholder={idx < 4 ? `第 ${idx + 1} 层原因` : "追溯到可采取措施的根因"}
                  />
                </Form.Item>
              </Col>
            </Row>
          ))}
          <Form.Item
            label="根因结论"
            name="root_cause"
            style={{ marginBottom: 10 }}
          >
            <Input.TextArea
              rows={2}
              placeholder="归纳 5 Whys 的根因，作为措施依据"
            />
          </Form.Item>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item
                label="分析人（班组长）"
                name="analyst"
                rules={[{ required: true, message: "请填写分析人" }]}
              >
                <Input placeholder="姓名" />
              </Form.Item>
            </Col>
          </Row>
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={saveAnalysis}
            >
              保存分析{analysisDirty ? "" : ""}
            </Button>
            {event.analysis && (
              <Popconfirm
                title="删除该分析记录？"
                onConfirm={async () => {
                  await api.deleteAnalysis(eventId);
                  message.success("已删除");
                  load();
                }}
              >
                <Button danger type="dashed">
                  删除分析
                </Button>
              </Popconfirm>
            )}
          </Space>
        </Form>
      </Card>

      <Card
        size="small"
        title="改善措施跟踪"
        extra={<ActionCreateModal eventId={eventId} onSaved={load} />}
      >
        {event.actions.length === 0 ? (
          <Paragraph type="secondary" style={{ margin: 0 }}>
            暂无改善措施，点击右上角「新增措施」
          </Paragraph>
        ) : (
          <Table
            rowKey="id"
            size="small"
            columns={actionColumns}
            dataSource={event.actions}
            pagination={false}
          />
        )}
      </Card>
    </div>
  );
}

function ActionCreateModal({
  eventId,
  onSaved,
}: {
  eventId: number;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await api.createAction(eventId, {
        content: v.content.trim(),
        owner: v.owner.trim(),
        due_date: v.due_date ? v.due_date.toISOString() : null,
        status: "open",
      });
      message.success("措施已添加");
      setOpen(false);
      form.resetFields();
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        size="small"
        onClick={() => setOpen(true)}
      >
        新增措施
      </Button>
      <Modal
        title="新增改善措施"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={submit}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="措施内容"
            name="content"
            rules={[{ required: true, message: "请填写措施" }]}
          >
            <Input.TextArea rows={2} />
          </Form.Item>
          <Space>
            <Form.Item
              label="责任人"
              name="owner"
              rules={[{ required: true, message: "请填写责任人" }]}
            >
              <Input />
            </Form.Item>
            <Form.Item label="计划完成日期" name="due_date">
              <DatePicker />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </>
  );
}

function ActionEditModal({
  action,
  eventId,
  onSaved,
}: {
  action: CorrectiveAction;
  eventId: number;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await api.updateAction(eventId, action.id, {
        content: v.content.trim(),
        owner: v.owner.trim(),
        due_date: v.due_date ? v.due_date.toISOString() : null,
      });
      message.success("已更新");
      setOpen(false);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button type="link" size="small" onClick={() => setOpen(true)}>
        编辑
      </Button>
      <Modal
        title="编辑改善措施"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={submit}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            content: action.content,
            owner: action.owner,
            due_date: action.due_date ? dayjs(action.due_date) : null,
          }}
        >
          <Form.Item
            label="措施内容"
            name="content"
            rules={[{ required: true, message: "请填写措施" }]}
          >
            <Input.TextArea rows={2} />
          </Form.Item>
          <Space>
            <Form.Item
              label="责任人"
              name="owner"
              rules={[{ required: true, message: "请填写责任人" }]}
            >
              <Input />
            </Form.Item>
            <Form.Item label="计划完成日期" name="due_date">
              <DatePicker />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </>
  );
}
