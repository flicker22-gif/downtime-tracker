import { Layout, Menu } from "antd";
import { DashboardOutlined, UnorderedListOutlined, ToolOutlined } from "@ant-design/icons";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import EventListPage from "./pages/EventListPage";
import EventDetailPage from "./pages/EventDetailPage";
import AnalysisPage from "./pages/AnalysisPage";
import ReliabilityPage from "./pages/ReliabilityPage";

const { Header, Sider, Content } = Layout;

export default function App() {
  const location = useLocation();
  let selectedKey = "events";
  if (location.pathname.startsWith("/analysis")) selectedKey = "analysis";
  if (location.pathname.startsWith("/reliability")) selectedKey = "reliability";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" breakpoint="lg" collapsedWidth="0">
        <div
          style={{
            color: "#fff",
            fontWeight: 600,
            fontSize: 15,
            textAlign: "center",
            padding: "18px 8px",
            letterSpacing: 1,
          }}
        >
          车间停机管理
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            {
              key: "events",
              icon: <UnorderedListOutlined />,
              label: <Link to="/">停机事件</Link>,
            },
            {
              key: "analysis",
              icon: <DashboardOutlined />,
              label: <Link to="/analysis">原因分析</Link>,
            },
            {
              key: "reliability",
              icon: <ToolOutlined />,
              label: <Link to="/reliability">设备可靠性</Link>,
            },
          ]}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            paddingInline: 24,
            fontWeight: 600,
            fontSize: 16,
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          停机事件登记与根因分析
        </Header>
        <Content style={{ margin: 16 }}>
          <Routes>
            <Route path="/" element={<EventListPage />} />
            <Route path="/events/:id" element={<EventDetailPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/reliability" element={<ReliabilityPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
