import { useEffect, useMemo, useState } from "react";
import {
  Form,
  Input,
  Modal,
  Select,
  DatePicker,
  InputNumber,
  AutoComplete,
  message,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { api } from "../api";
import type { Equipment, EventCreatePayload, Line, Reason } from "../types";

const { RangePicker } = DatePicker;

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  lines: Line[];
  reasons: Reason[];
}

interface FormValues {
  line_id: number;
  equipment_id: number;
  range: [Dayjs, Dayjs | null];
  duration_min?: number | null;
  shift: string;
  reporter: string;
  reason_id: number;
  product?: string;
  note?: string;
}

const SHIFT_OPTIONS = [
  { value: "白班", label: "白班" },
  { value: "夜班", label: "夜班" },
];

export default function EventCreateModal({
  open,
  onClose,
  onCreated,
  lines,
  reasons,
}: Props) {
  const [form] = Form.useForm<FormValues>();
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [allEquipments, setAllEquipments] = useState<Equipment[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [reporters, setReporters] = useState<string[]>([]);

  useEffect(() => {
    api.listEquipments().then(setAllEquipments).catch(() => undefined);
  }, []);

  // 从近期事件里收集操作工姓名，做自动补全
  useEffect(() => {
    api
      .listEvents({ page: 1, page_size: 50 })
      .then((res) => {
        const names = Array.from(new Set(res.items.map((i) => i.reporter)));
        setReporters(names);
      })
      .catch(() => undefined);
  }, [open]);

  const lineId = Form.useWatch("line_id", form);

  useEffect(() => {
    if (lineId) {
      setEquipments(allEquipments.filter((e) => e.line_id === lineId));
    } else {
      setEquipments([]);
    }
  }, [lineId, allEquipments]);

  const reasonOptions = useMemo(() => {
    const groups = new Map<string, Reason[]>();
    reasons.forEach((r) => {
      const arr = groups.get(r.category) ?? [];
      arr.push(r);
      groups.set(r.category, arr);
    });
    return Array.from(groups.entries()).map(([cat, items]) => ({
      label: cat,
      options: items.map((r) => ({ value: r.id, label: r.name })),
    }));
  }, [reasons]);

  const handleOk = async () => {
    const values = await form.validateFields();
    const [start, end] = values.range;
    let duration = values.duration_min;
    if (duration == null && end) {
      duration = Math.round(end.diff(start, "minute", true));
    }
    const payload: EventCreatePayload = {
      line_id: values.line_id,
      equipment_id: values.equipment_id,
      reason_id: values.reason_id,
      start_time: start.toISOString(),
      end_time: end ? end.toISOString() : null,
      duration_min: duration ?? null,
      shift: values.shift,
      reporter: values.reporter.trim(),
      product: values.product?.trim() || null,
      note: values.note?.trim() || null,
    };
    setSubmitting(true);
    try {
      await api.createEvent(payload);
      message.success("停机事件已登记");
      form.resetFields();
      onCreated();
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      message.error(
        typeof detail === "string" ? detail : "登记失败，请检查输入"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="登记停机事件"
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={submitting}
      okText="提交登记"
      cancelText="取消"
      width={640}
      destroyOnClose
      maskClosable={false}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          range: [dayjs(), null],
          shift: dayjs().hour() >= 8 && dayjs().hour() < 20 ? "白班" : "夜班",
        }}
      >
        <Form.Item
          label="产线"
          name="line_id"
          rules={[{ required: true, message: "请选择产线" }]}
        >
          <Select
            placeholder="选择产线"
            options={lines.map((l) => ({ value: l.id, label: l.name }))}
            onChange={() => form.setFieldValue("equipment_id", undefined)}
          />
        </Form.Item>

        <Form.Item
          label="设备"
          name="equipment_id"
          rules={[{ required: true, message: "请选择设备" }]}
        >
          <Select
            placeholder={lineId ? "选择设备" : "请先选择产线"}
            disabled={!lineId}
            options={equipments.map((e) => ({
              value: e.id,
              label: `${e.code} ${e.name}`,
            }))}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

        <Form.Item
          label="停机原因"
          name="reason_id"
          rules={[{ required: true, message: "请选择停机原因" }]}
        >
          <Select
            placeholder="按大类选择停机原因"
            options={reasonOptions}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

        <Form.Item
          label="停机时间（开始 ~ 结束，结束可后补）"
          name="range"
          rules={[
            { required: true, message: "请选择停机开始时间" },
            {
              validator: (_, value: [Dayjs, Dayjs | null]) => {
                if (value?.[1] && value[1].isBefore(value[0])) {
                  return Promise.reject(new Error("结束时间不能早于开始时间"));
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <RangePicker showTime style={{ width: "100%" }} />
        </Form.Item>

        <Form.Item
          label="停机时长（分钟，留空则按起止时间自动计算）"
          name="duration_min"
        >
          <InputNumber min={0} step={5} style={{ width: "100%" }} />
        </Form.Item>

        <div style={{ display: "flex", gap: 12 }}>
          <Form.Item
            label="班次"
            name="shift"
            style={{ flex: 1 }}
            rules={[{ required: true, message: "请选择班次" }]}
          >
            <Select options={SHIFT_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="操作工"
            name="reporter"
            style={{ flex: 1 }}
            rules={[{ required: true, message: "请填写操作工" }]}
          >
            <AutoComplete
              placeholder="登记人工号/姓名"
              options={reporters.map((r) => ({ value: r }))}
              filterOption={(input, option) =>
                (option?.value ?? "").includes(input)
              }
            >
              <Input />
            </AutoComplete>
          </Form.Item>
          <Form.Item label="工单/产品" name="product" style={{ flex: 1 }}>
            <Input placeholder="选填" />
          </Form.Item>
        </div>

        <Form.Item label="备注" name="note">
          <Input.TextArea rows={2} placeholder="选填，记录停机现象等" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
