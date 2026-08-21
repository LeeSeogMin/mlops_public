"""
데이터 파이프라인 시각화

실시간 데이터 파이프라인의 기본 구조를 시각화합니다.
학습 목표: 실시간 데이터 파이프라인의 기본 구조를 도식화할 수 있다.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from typing import List, Tuple, Dict
import os


class PipelineVisualizer:
    """데이터 파이프라인 시각화 도구"""

    # 컴포넌트 색상
    COLORS = {
        "source": "#4CAF50",       # 녹색 - 데이터 소스
        "ingestion": "#2196F3",    # 파랑 - 수집
        "processing": "#FF9800",   # 주황 - 처리
        "storage": "#9C27B0",      # 보라 - 저장
        "serving": "#F44336",      # 빨강 - 서빙
        "monitoring": "#607D8B",   # 회색 - 모니터링
    }

    def __init__(self, figsize: Tuple[int, int] = (14, 8)):
        self.figsize = figsize

    def draw_component(self, ax, x: float, y: float, width: float, height: float,
                       label: str, color: str, sublabel: str = None):
        """컴포넌트 박스 그리기"""
        box = FancyBboxPatch(
            (x - width/2, y - height/2),
            width, height,
            boxstyle="round,pad=0.05,rounding_size=0.1",
            facecolor=color,
            edgecolor='white',
            linewidth=2,
            alpha=0.9
        )
        ax.add_patch(box)

        # 메인 레이블
        ax.text(x, y + (0.1 if sublabel else 0), label,
                ha='center', va='center',
                fontsize=10, fontweight='bold', color='white')

        # 서브 레이블
        if sublabel:
            ax.text(x, y - 0.15, sublabel,
                    ha='center', va='center',
                    fontsize=8, color='white', alpha=0.9)

    def draw_arrow(self, ax, start: Tuple[float, float], end: Tuple[float, float],
                   color: str = 'gray', style: str = 'solid'):
        """화살표 그리기"""
        linestyle = '-' if style == 'solid' else '--'
        ax.annotate('',
                    xy=end,
                    xytext=start,
                    arrowprops=dict(
                        arrowstyle='->',
                        color=color,
                        lw=2,
                        linestyle=linestyle
                    ))

    def create_basic_pipeline(self, save_path: str = None) -> plt.Figure:
        """
        기본 DE-MLOps 통합 파이프라인 시각화

        데이터 수집 → 처리 → 저장 → 피처 스토어 → ML 모델 → 서빙
        """
        fig, ax = plt.subplots(figsize=self.figsize)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 6)
        ax.axis('off')
        ax.set_aspect('equal')

        # 제목
        ax.text(5, 5.5, '공공 데이터 파이프라인 기본 구조',
                ha='center', va='center', fontsize=14, fontweight='bold')

        # 컴포넌트 위치 정의
        components = [
            # (x, y, width, height, label, sublabel, color_key)
            (1, 4, 1.2, 0.7, "민원 API", "실시간", "source"),
            (1, 3, 1.2, 0.7, "재난 API", "이벤트", "source"),
            (1, 2, 1.2, 0.7, "교통 센서", "스트림", "source"),

            (3, 3, 1.2, 0.7, "Kafka", "이벤트 버스", "ingestion"),

            (5, 4, 1.4, 0.7, "Spark\nStreaming", "실시간 처리", "processing"),
            (5, 2, 1.4, 0.7, "Spark\nBatch", "배치 처리", "processing"),

            (7, 4, 1.2, 0.7, "피처\n스토어", "Feast", "storage"),
            (7, 2, 1.2, 0.7, "데이터\n레이크", "S3/HDFS", "storage"),

            (9, 3.5, 1.2, 0.7, "ML 모델", "추론", "serving"),
            (9, 2.5, 1.2, 0.7, "대시보드", "Grafana", "serving"),
        ]

        # 컴포넌트 그리기
        for x, y, w, h, label, sublabel, color_key in components:
            self.draw_component(ax, x, y, w, h, label, self.COLORS[color_key], sublabel)

        # 화살표 (데이터 흐름)
        arrows = [
            ((1.6, 4), (2.4, 3.3)),    # 민원 → Kafka
            ((1.6, 3), (2.4, 3)),      # 재난 → Kafka
            ((1.6, 2), (2.4, 2.7)),    # 교통 → Kafka

            ((3.6, 3.3), (4.3, 4)),    # Kafka → Streaming
            ((3.6, 2.7), (4.3, 2)),    # Kafka → Batch

            ((5.7, 4), (6.4, 4)),      # Streaming → 피처스토어
            ((5.7, 2), (6.4, 2)),      # Batch → 레이크

            ((7.6, 4), (8.4, 3.5)),    # 피처스토어 → ML
            ((7.6, 2), (8.4, 2.5)),    # 레이크 → 대시보드
        ]

        for start, end in arrows:
            self.draw_arrow(ax, start, end, color='#333333')

        # 범례
        legend_elements = [
            mpatches.Patch(color=self.COLORS["source"], label='데이터 소스'),
            mpatches.Patch(color=self.COLORS["ingestion"], label='수집'),
            mpatches.Patch(color=self.COLORS["processing"], label='처리'),
            mpatches.Patch(color=self.COLORS["storage"], label='저장'),
            mpatches.Patch(color=self.COLORS["serving"], label='서빙'),
        ]
        ax.legend(handles=legend_elements, loc='lower right', fontsize=9)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            print(f"파이프라인 다이어그램 저장: {save_path}")

        return fig

    def create_de_mlops_comparison(self, save_path: str = None) -> plt.Figure:
        """DE vs MLOps 역할 비교 시각화"""
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # DE 영역
        ax1 = axes[0]
        ax1.set_xlim(0, 5)
        ax1.set_ylim(0, 5)
        ax1.axis('off')
        ax1.set_title('데이터 엔지니어링 (DE)', fontsize=12, fontweight='bold', pad=20)

        de_components = [
            (2.5, 4, "수집 (Ingestion)", "Kafka, API 폴링"),
            (2.5, 3, "저장 (Storage)", "데이터 레이크, DW"),
            (2.5, 2, "변환 (Transform)", "ETL/ELT 파이프라인"),
            (2.5, 1, "제공 (Serving)", "피처 스토어, API"),
        ]

        for x, y, label, desc in de_components:
            self.draw_component(ax1, x, y, 3, 0.7, label, self.COLORS["ingestion"], desc)

        # MLOps 영역
        ax2 = axes[1]
        ax2.set_xlim(0, 5)
        ax2.set_ylim(0, 5)
        ax2.axis('off')
        ax2.set_title('MLOps', fontsize=12, fontweight='bold', pad=20)

        mlops_components = [
            (2.5, 4, "개발 (Development)", "실험, 피처 엔지니어링"),
            (2.5, 3, "배포 (Deployment)", "모델 서빙, A/B 테스트"),
            (2.5, 2, "모니터링 (Monitoring)", "성능 추적, 드리프트"),
            (2.5, 1, "재학습 (Retraining)", "자동화된 갱신"),
        ]

        for x, y, label, desc in mlops_components:
            self.draw_component(ax2, x, y, 3, 0.7, label, self.COLORS["serving"], desc)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            print(f"비교 다이어그램 저장: {save_path}")

        return fig

    def create_public_sector_requirements(self, save_path: str = None) -> plt.Figure:
        """공공 영역 특수 요구사항 시각화"""
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis('off')

        ax.text(5, 9.5, '공공 영역 DE-MLOps 특수 요구사항',
                ha='center', va='center', fontsize=14, fontweight='bold')

        # 중앙 원
        center_circle = plt.Circle((5, 5), 1.5, color=self.COLORS["processing"],
                                    alpha=0.3, ec=self.COLORS["processing"], lw=2)
        ax.add_patch(center_circle)
        ax.text(5, 5, 'DE-MLOps\n통합 시스템', ha='center', va='center',
                fontsize=11, fontweight='bold')

        # 4가지 요구사항
        requirements = [
            (5, 8, "규제 준수", "개인정보보호법\n공공데이터법", self.COLORS["source"]),
            (8, 5, "감사 추적", "데이터 접근 로그\n변경 이력 기록", self.COLORS["ingestion"]),
            (5, 2, "투명성", "AI 의사결정 설명\n시민 대상 공개", self.COLORS["storage"]),
            (2, 5, "예산 제약", "비용 효율적 설계\n클라우드 최적화", self.COLORS["serving"]),
        ]

        for x, y, title, desc, color in requirements:
            # 외부 원
            outer_circle = plt.Circle((x, y), 1.2, color=color, alpha=0.8)
            ax.add_patch(outer_circle)
            ax.text(x, y + 0.3, title, ha='center', va='center',
                    fontsize=10, fontweight='bold', color='white')
            ax.text(x, y - 0.3, desc, ha='center', va='center',
                    fontsize=8, color='white')

            # 연결선
            dx, dy = 5 - x, 5 - y
            length = np.sqrt(dx**2 + dy**2)
            # 시작점과 끝점 조정
            start_x = x + (dx/length) * 1.2
            start_y = y + (dy/length) * 1.2
            end_x = 5 - (dx/length) * 1.5
            end_y = 5 - (dy/length) * 1.5
            ax.plot([start_x, end_x], [start_y, end_y],
                    color='gray', lw=2, linestyle='--', alpha=0.5)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            print(f"요구사항 다이어그램 저장: {save_path}")

        return fig


def demo():
    """데모 실행"""
    print("=" * 60)
    print("파이프라인 시각화 데모")
    print("=" * 60)

    output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(output_dir, exist_ok=True)

    visualizer = PipelineVisualizer()

    print("\n[1] 기본 파이프라인 다이어그램 생성...")
    visualizer.create_basic_pipeline(
        save_path=os.path.join(output_dir, "basic_pipeline.png")
    )

    print("\n[2] DE vs MLOps 비교 다이어그램 생성...")
    visualizer.create_de_mlops_comparison(
        save_path=os.path.join(output_dir, "de_mlops_comparison.png")
    )

    print("\n[3] 공공 영역 요구사항 다이어그램 생성...")
    visualizer.create_public_sector_requirements(
        save_path=os.path.join(output_dir, "public_sector_requirements.png")
    )

    print("\n" + "=" * 60)
    print(f"모든 다이어그램이 {output_dir}에 저장되었습니다.")


if __name__ == "__main__":
    demo()
