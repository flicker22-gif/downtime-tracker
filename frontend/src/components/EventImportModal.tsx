import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import {
  DownloadOutlined,
  FileExcelOutlined,
  InboxOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { api } from "../api";
import {
  ImportBatch,
  ImportRow,
  ImportRowStatus,
  IMPORT_ROW_STATUS_META,
} from "../types";

const { Dragger } = Upload;
const { Text } = Typography;

const TEMPLATE_HEADERS = [
  "external_event_no", "line_code", "equipment_code", "reason_code",
  "start_time", "end_time", "duration_min", "shift", "reporter", "product", "note",
];
const TEMPLATE_EXAMPLE = [
  "EXP001", "L1", "P101", "EQ_MECH", "2026-09-14 08:30", "2026-09-14 09:15",
  "45", "白班", "张三", "WO-1001", "示例行可删除",
];

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}

export default function EventImportModal({ open, onClose, onImported }: Props) {
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [rows, setRows] = useState<ImportRow[]>([]);
  const [rowsTotal, setRowsTotal] = useState(0);
  const [rowStatus, setRowStatus] = useState<ImportRowStatus | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmErrors, setConfirmErrors] = useState<string[]>([]);

  const reset = useCallback(() => {
    setBatch(null);
    setRows([]);
    setRowsTotal(0);
    setRowStatus(undefined);
    setPage(1);
    setConfirmErrors([]);
  }, []);

  useEffect(() => {
    if (open) reset();
  }, [open, reset]);

  const loadRows = useCallback(async () => {
    if (!batch) return;
    try {
      const res = await api.listImportRows(batch.id, {
        status: rowStatus,
        page,
        page_size: pageSize,
      });
      setRows(res.items);
      setRowsTotal(res.total);
    } catch {
      message.error("加载预检明细失败");
    }
  }, [batch, rowStatus, page, pageSize]);

  useEffect(() => {
    loadRows();
  }, [loadRows]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setConfirmErrors([]);
    try {
      const b = await api.precheckImport(file);
      setBatch(b);
      setPage(1);
      setRowStatus(undefined);
      if (b.deduplicated) {
        message.info("文件内容相同，已命中历史导入批次");
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      message.error(typeof detail === "string" ? detail : "预检失败，请检查文件");
    } finally {
      setUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!batch) return;
    setConfirming(true);
    setConfirmErrors([]);
    try {
      const res = await api.confirmImport(batch.id);
      setBatch(res.batch);
      message.success(
        `导入完成：写入 ${res.imported} 条` +
          (res.skipped ? `，跳过重复 ${res.skipped} 条` : "")
      );
      onImported();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.rows) {
        setConfirmErrors(
          (detail.rows as { row_no: number; errors: string[] }[]).map(
            (r) => `第 ${r.row_no} 行：${r.errors.join("；")}`
          )
        );
        message.error(detail.message ?? "导入失败，已整体回滚");
      } else {
        message.error(typeof detail === "string" ? detail : "导入失败");
      }
    } finally {
      setConfirming(false);
    }
  };

  const handleDownloadErrors = async () => {
    if (!batch) return;
    const blob = await api.downloadImportErrors(batch.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `import_${batch.id}_errors.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadTemplate = () => {
    // 带 BOM 的 UTF-8：Excel 直接打开中文表头不乱码
    const content =
      "\uFEFF" + TEMPLATE_HEADERS.join(",") + "\n" + TEMPLATE_EXAMPLE.join(",") + "\n";
    const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "downtime_import_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const committed = batch?.status === "committed";
  const confirmable =
    !!batch && !committed && batch.ok_rows > 0 &&
    batch.error_rows === 0 && batch.conflict_rows === 0;

  const columns: ColumnsType<ImportRow> = [
    { title: "行号", dataIndex: "row_no", width: 60 },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (s: ImportRowStatus) => (
        <Tag color={IMPORT_ROW_STATUS_META[s].color}>
          {IMPORT_ROW_STATUS_META[s].label}
        </Tag>
      ),
    },
    {
      title: "外部事件号",
      width: 110,
      render: (_, r) => r.data.external_event_no ?? "—",
    },
    { title: "产线", width: 80, render: (_, r) => r.data.line_code },
    { title: "设备", width: 90, render: (_, r) => r.data.equipment_code },
    {
      title: "开始时间",
      width: 140,
      render: (_, r) =>
        r.data.start_time ? dayjs(r.data.start_time).format("MM-DD HH:mm") : "—",
    },
    {
      title: "时长(分)",
      width: 80,
      align: "right",
      render: (_, r) => r.data.duration_min ?? "—",
    },
    { title: "班次", width: 60, render: (_, r) => r.data.shift },
    { title: "操作工", width: 80, render: (_, r) => r.data.reporter },
    {
      title: "事件编号",
      width: 140,
      render: (_, r) => r.event_no ?? "—",
    },
    {
      title: "说明",
      render: (_, r) =>
        r.errors.length ? (
          <Text type="danger">{r.errors.join("；")}</Text>
        ) : (
          "—"
        ),
    },
  ];

  return (
    <Modal
      title="CSV 批量导入停机事件"
      open={open}
      onCancel={onClose}
      width={1080}
      maskClosable={false}
      footer={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          {batch && !committed && (
            <Button icon={<ReloadOutlined />} onClick={reset}>
              重新上传
            </Button>
          )}
          {batch && (batch.error_rows > 0 || batch.conflict_rows > 0) && (
            <Button icon={<DownloadOutlined />} onClick={handleDownloadErrors}>
              下载需修正行
            </Button>
          )}
          {!committed && (
            <Button
              type="primary"
              disabled={!confirmable}
              loading={confirming}
              onClick={handleConfirm}
            >
              确认导入{batch && batch.ok_rows > 0 ? ` ${batch.ok_rows} 条` : ""}
            </Button>
          )}
        </Space>
      }
    >
      {!batch ? (
        <>
          <Dragger
            accept=".csv"
            maxCount={1}
            showUploadList={false}
            customRequest={({ file }) => handleUpload(file as File)}
            disabled={uploading}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              {uploading ? "预检中…" : "点击或拖拽 CSV 文件到此处上传预检"}
            </p>
            <p className="ant-upload-hint">
              支持 UTF-8 / GBK 编码；单文件最多 10000 行。
              同一文件重复上传自动幂等，不会重复导入。
            </p>
          </Dragger>
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message={
              <Space>
                必需列：产线编码、设备编码、原因编码、开始时间、班次、操作工；
                外部事件号可空（设备日志导出号，用于跨文件去重）。
                <Button
                  size="small"
                  icon={<FileExcelOutlined />}
                  onClick={downloadTemplate}
                >
                  下载模板
                </Button>
              </Space>
            }
          />
        </>
      ) : (
        <>
          <Alert
            style={{ marginBottom: 12 }}
            type={
              committed
                ? "success"
                : batch.error_rows + batch.conflict_rows > 0
                ? "warning"
                : "info"
            }
            showIcon
            message={
              committed
                ? `「${batch.filename}」已完成导入：写入 ${batch.imported_rows} 条` +
                  (batch.skipped_rows ? `，跳过重复 ${batch.skipped_rows} 条` : "")
                : `「${batch.filename}」预检完成：共 ${batch.total_rows} 行，` +
                  `可导入 ${batch.ok_rows}，重复 ${batch.duplicate_rows}，` +
                  `冲突 ${batch.conflict_rows}，需修正 ${batch.error_rows}`
            }
            description={
              committed
                ? undefined
                : batch.error_rows + batch.conflict_rows > 0
                ? "存在不可导入的行时无法确认导入。请下载需修正行，修正后重新上传预检。"
                : "重复行将在导入时自动跳过；确认后在事务内批量写入。"
            }
          />
          {confirmErrors.length > 0 && (
            <Alert
              style={{ marginBottom: 12 }}
              type="error"
              showIcon
              message="确认导入失败，已整体回滚"
              description={
                <div style={{ maxHeight: 120, overflow: "auto" }}>
                  {confirmErrors.map((e) => (
                    <div key={e}>{e}</div>
                  ))}
                </div>
              }
            />
          )}
          <Space style={{ marginBottom: 8 }}>
            <Text type="secondary">行筛选</Text>
            <Select
              allowClear
              placeholder="全部状态"
              style={{ width: 140 }}
              value={rowStatus}
              onChange={(v) => {
                setRowStatus(v);
                setPage(1);
              }}
              options={(
                Object.keys(IMPORT_ROW_STATUS_META) as ImportRowStatus[]
              ).map((k) => ({ value: k, label: IMPORT_ROW_STATUS_META[k].label }))}
            />
          </Space>
          <Table
            rowKey="row_no"
            size="small"
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1100, y: 380 }}
            pagination={{
              current: page,
              pageSize,
              total: rowsTotal,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 行`,
              onChange: (p, ps) => {
                setPage(p);
                setPageSize(ps);
              },
            }}
          />
        </>
      )}
    </Modal>
  );
}
