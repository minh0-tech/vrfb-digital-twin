---
title: VRFB Digital Twin LCOS Platform
emoji: 🔋
colorFrom: blue
colorTo: green
sdk: gradio
app_file: app.py
pinned: false
---

# VRFB v24 Web Platform

문헌 기반 VRFB 물리모델, 20년 LCOS, 설계 민감도, reduced-order Digital Twin을 하나의 웹 앱으로 통합한 데모입니다.

## Railway
이 저장소를 Railway에 연결하면 `railway.toml`의 `python app.py` 명령으로 실행됩니다. 앱은 Railway의 `PORT` 환경변수를 자동 인식합니다.

## 모델 주의
Digital Twin의 Projected LCOS는 실시간 효율 변화를 장기 에너지비에 투영하는 screening 지표이며, 매 순간 20년 열화/교체 경로 전체를 재적분하는 full predictive LCOS는 아닙니다.
