# SolarPilot

[![Flutter](https://img.shields.io/badge/Flutter-3.16+-blue.svg)](https://flutter.dev/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**智能光储调度系统** - 基于物理模型的太阳能预测与电池能量管理系统

![Overview](https://via.placeholder.com/800x400/4CAF50/FFFFFF?text=SolarPilot+Overview)

## 🌟 核心功能

### ☀️ 太阳能预测
- 基于物理模型的 PV 功率预测
- P10/P50/P90 概率预测
- 清空模型 + NWP 数据融合
- 自动校准（PR、污损系数）

### ⚡ 能量调度优化
- MILP 优化调度策略
- 考虑分时电价、需量电费
- 电池充放电优化
- 削峰填谷、弃光最小化

### 📊 模型监控
- 实时预测精度验证
- 模型漂移检测（绿/黄/红）
- 自动触发重新校准
- 完整审计日志

### 📱 移动应用
- Flutter 跨平台 App
- 实时 KPI 看板
- 交互式图表展示
- 告警管理系统

## 🚀 快速开始

### 方式 1: Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/sedai-solar2grid.git
cd sedai-solar2grid

# 启动所有服务
cd infra
docker-compose up -d

# 访问服务
# API Gateway: http://localhost:8000
# Forecast Service: http://localhost:8001
# Dispatch Service: http://localhost:8002
```

### 方式 2: 本地开发

```bash
# 1. 启动数据库
cd infra
docker-compose up -d db

# 2. 启动后端服务
cd ../services/forecast_service
pip install -r requirements.txt
python main.py

# 3. 启动 Flutter App
cd ../../apps/mobile_flutter
flutter pub get
flutter run -d chrome
```

## 📱 在线演示

- **Web App**: https://sedai-solar2grid.vercel.app
- **API 文档**: https://sedai-solar2grid.railway.app/docs
- **演示视频**: [YouTube Link](#)

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter Mobile App                    │
│         (iOS / Android / Web / Desktop)                 │
└────────────────────┬────────────────────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────────────────────┐
│                   API Gateway (FastAPI)                  │
└──────┬─────────────────────────────────────────┬────────┘
       │                                          │
┌──────▼────────────┐                  ┌─────────▼────────┐
│ Forecast Service  │                  │ Dispatch Service │
│  - Physics Model  │                  │  - MILP Solver   │
│  - Validation     │                  │  - Optimization  │
│  - Calibration    │                  │  - Fallback      │
└──────┬────────────┘                  └─────────┬────────┘
       │                                          │
       └──────────────┬───────────────────────────┘
                      │
            ┌─────────▼──────────┐
            │  TimescaleDB       │
            │  - Time Series     │
            │  - Audit Logs      │
            └────────────────────┘
```

## 📂 项目结构

```
sedai-solar2grid/
├── apps/
│   └── mobile_flutter/          # Flutter 移动应用
│       ├── lib/
│       │   ├── pages/           # 页面（Overview, Forecast, Dispatch, Alerts）
│       │   ├── providers/       # Riverpod 状态管理
│       │   └── core/api/        # API 客户端
│       └── pubspec.yaml
├── services/
│   ├── api_gateway/             # API 网关
│   ├── forecast_service/        # 预测服务
│   │   ├── models/              # 物理模型、ML模型
│   │   ├── validation/          # 验证、漂移检测、校准
│   │   └── main.py
│   ├── dispatch_service/        # 调度服务
│   │   ├── optimization/        # MILP 优化器
│   │   └── main.py
│   └── shared/                  # 共享模块
│       └── audit_logger.py      # 审计日志
├── infra/
│   ├── docker-compose.yml       # Docker 编排
│   └── db/init.sql              # 数据库初始化
├── docs/                        # 文档
└── README.md
```

## 🛠️ 技术栈

### 后端
- **FastAPI** - 高性能 API 框架
- **SQLAlchemy** - ORM
- **TimescaleDB** - 时序数据库
- **PuLP** - MILP 优化求解器
- **NumPy / Pandas** - 数据处理

### 前端
- **Flutter** - 跨平台 UI 框架
- **Riverpod** - 状态管理
- **fl_chart** - 图表库
- **Dio** - HTTP 客户端

### DevOps
- **Docker / Docker Compose** - 容器化
- **GitHub Actions** - CI/CD
- **Vercel / Railway** - 部署平台

## 📊 功能模块

### 1. 预测引擎
- ✅ 基线物理模型（clear sky + PR + 温度修正）
- ✅ NWP 数据集成（云层、温度、辐照）
- ✅ 概率预测（P10/P50/P90）
- ✅ 自动回退机制（NWP 不可用时）

### 2. 验证与校准
- ✅ KPI 计算（MAE, RMSE, NRMSE, Bias, R²）
- ✅ 漂移检测（30天基线 vs 7天滚动窗口）
- ✅ 自动校准（线性偏差调整 + 参数约束）
- ✅ 健康状态监控（GREEN/AMBER/RED）

### 3. 调度优化
- ✅ MILP 求解器（最小化成本 + 约束）
- ✅ 分时电价支持
- ✅ 需量电费考虑
- ✅ 电池寿命管理（SOC 约束）
- ✅ 削峰填谷策略
- ✅ 启发式回退方案

### 4. 审计与报告
- ✅ 全参数审计日志（请求、结果、版本、运行时）
- ✅ CSV 报告导出（调度计划、预测结果）
- ✅ 性能指标追踪

### 5. 移动应用
- ✅ Overview 看板（KPI、模型健康）
- ✅ Forecast 页面（图表、驱动因素）
- ✅ Dispatch 页面（时间轴、原因解释）
- ✅ Alerts 页面（告警管理、ACK 确认）
- ✅ Sites 管理

## 📖 文档

- [快速开始指南](QUICKSTART.md)
- [API 文档](docs/API.md)
- [部署指南](docs/DEPLOYMENT.md)
- [验证系统文档](docs/VALIDATION.md)
- [架构设计](docs/ARCHITECTURE.md)

## 🧪 测试

```bash
# 后端测试
cd services/forecast_service
pytest tests/

# Flutter 测试
cd apps/mobile_flutter
flutter test
```

## 🤝 贡献指南

欢迎提交 Pull Request！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙋 联系方式

- **项目主页**: https://github.com/YOUR_USERNAME/sedai-solar2grid
- **问题反馈**: https://github.com/YOUR_USERNAME/sedai-solar2grid/issues
- **讨论区**: https://github.com/YOUR_USERNAME/sedai-solar2grid/discussions

## 🎯 路线图

- [x] 基础物理预测模型
- [x] MILP 调度优化
- [x] 验证与校准系统
- [x] 审计日志
- [x] Flutter 移动应用
- [ ] ML 模型集成（LSTM/Transformer）
- [ ] 实时 IoT 数据采集
- [ ] 多站点协同优化
- [ ] 碳排放追踪
- [ ] 移动端离线模式

## ⭐ Star History

如果这个项目对您有帮助，请给我们一个 Star！

[![Star History Chart](https://api.star-history.com/svg?repos=YOUR_USERNAME/sedai-solar2grid&type=Date)](https://star-history.com/#YOUR_USERNAME/sedai-solar2grid&Date)

---

**Built with ❤️ by SEDAI Team**
