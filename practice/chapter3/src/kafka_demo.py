"""
Kafka 프로듀서/컨슈머 시뮬레이션

실습 3.1: Docker Compose 기반 파이프라인 구성
- Kafka 토픽 생성 시뮬레이션
- 프로듀서/컨슈머 동작 시뮬레이션
- 실제 Kafka 연결 시 사용 가능한 코드 제공

Note: 이 코드는 Kafka 없이도 동작하는 시뮬레이션입니다.
      실제 Kafka 연결 시 kafka-python 패키지 필요.
"""

import json
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import deque
import threading


@dataclass
class KafkaMessage:
    """Kafka 메시지 구조"""
    topic: str
    partition: int
    offset: int
    key: Optional[str]
    value: Dict[str, Any]
    timestamp: str


class KafkaTopicSimulator:
    """Kafka 토픽 시뮬레이터"""

    def __init__(self):
        self.topics: Dict[str, Dict] = {}
        self.messages: Dict[str, deque] = {}
        self.offsets: Dict[str, int] = {}

    def create_topic(self, topic_name: str, partitions: int = 1,
                     replication_factor: int = 1) -> bool:
        """토픽 생성"""
        if topic_name in self.topics:
            return False

        self.topics[topic_name] = {
            "partitions": partitions,
            "replication_factor": replication_factor,
            "created_at": datetime.now().isoformat(),
            "config": {
                "retention.ms": 604800000,  # 7일
                "cleanup.policy": "delete",
            }
        }
        self.messages[topic_name] = deque(maxlen=10000)
        self.offsets[topic_name] = 0
        return True

    def list_topics(self) -> List[str]:
        """토픽 목록"""
        return list(self.topics.keys())

    def describe_topic(self, topic_name: str) -> Optional[Dict]:
        """토픽 상세 정보"""
        return self.topics.get(topic_name)

    def delete_topic(self, topic_name: str) -> bool:
        """토픽 삭제"""
        if topic_name not in self.topics:
            return False
        del self.topics[topic_name]
        del self.messages[topic_name]
        del self.offsets[topic_name]
        return True


class KafkaProducerSimulator:
    """Kafka 프로듀서 시뮬레이터"""

    def __init__(self, topic_simulator: KafkaTopicSimulator,
                 bootstrap_servers: str = "localhost:9092"):
        self.topic_simulator = topic_simulator
        self.bootstrap_servers = bootstrap_servers
        self.sent_count = 0

        # 프로듀서 설정 (공공 영역 권장)
        self.config = {
            "acks": "all",
            "enable.idempotence": True,
            "max.in.flight.requests.per.connection": 5,
            "retries": 3,
            "compression.type": "snappy",
        }

    def send(self, topic: str, value: Dict, key: Optional[str] = None) -> KafkaMessage:
        """메시지 전송"""
        if topic not in self.topic_simulator.topics:
            self.topic_simulator.create_topic(topic)

        offset = self.topic_simulator.offsets[topic]
        self.topic_simulator.offsets[topic] += 1

        message = KafkaMessage(
            topic=topic,
            partition=0,  # 단순화
            offset=offset,
            key=key,
            value=value,
            timestamp=datetime.now().isoformat(),
        )

        self.topic_simulator.messages[topic].append(message)
        self.sent_count += 1

        return message

    def flush(self):
        """버퍼 플러시 (시뮬레이션)"""
        pass

    def close(self):
        """프로듀서 종료"""
        self.flush()


class KafkaConsumerSimulator:
    """Kafka 컨슈머 시뮬레이터"""

    def __init__(self, topic_simulator: KafkaTopicSimulator,
                 group_id: str = "default-group",
                 bootstrap_servers: str = "localhost:9092"):
        self.topic_simulator = topic_simulator
        self.group_id = group_id
        self.bootstrap_servers = bootstrap_servers
        self.subscribed_topics: List[str] = []
        self.consumed_offsets: Dict[str, int] = {}

        # 컨슈머 설정
        self.config = {
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
            "max.poll.records": 500,
        }

    def subscribe(self, topics: List[str]):
        """토픽 구독"""
        self.subscribed_topics = topics
        for topic in topics:
            if topic not in self.consumed_offsets:
                self.consumed_offsets[topic] = 0

    def poll(self, timeout_ms: int = 1000, max_records: int = 10) -> List[KafkaMessage]:
        """메시지 폴링"""
        messages = []

        for topic in self.subscribed_topics:
            if topic not in self.topic_simulator.messages:
                continue

            topic_messages = self.topic_simulator.messages[topic]
            current_offset = self.consumed_offsets.get(topic, 0)

            for msg in topic_messages:
                if msg.offset >= current_offset and len(messages) < max_records:
                    messages.append(msg)
                    self.consumed_offsets[topic] = msg.offset + 1

        return messages

    def close(self):
        """컨슈머 종료"""
        pass


class PublicDataKafkaDemo:
    """공공 데이터 Kafka 데모"""

    # 토픽 정의
    TOPICS = {
        "complaints": {
            "partitions": 3,
            "description": "민원 데이터",
        },
        "disasters": {
            "partitions": 2,
            "description": "재난 경보",
        },
        "traffic": {
            "partitions": 6,
            "description": "교통 센서 데이터",
        },
        "environment": {
            "partitions": 2,
            "description": "환경 측정 데이터",
        },
    }

    def __init__(self):
        self.topic_simulator = KafkaTopicSimulator()
        self.producer = KafkaProducerSimulator(self.topic_simulator)
        self.consumer = KafkaConsumerSimulator(self.topic_simulator)

    def setup_topics(self):
        """토픽 설정"""
        print("\n[Kafka 토픽 생성]")
        print("-" * 60)

        for topic_name, config in self.TOPICS.items():
            success = self.topic_simulator.create_topic(
                topic_name,
                partitions=config["partitions"],
            )
            status = "생성됨" if success else "이미 존재"
            print(f"  토픽: {topic_name:15} 파티션: {config['partitions']} - {status}")

    def generate_sample_data(self, data_type: str) -> Dict:
        """샘플 데이터 생성"""
        regions = ["11", "26", "27", "28", "41", "42", "43", "44"]
        issue_types = ["road_repair", "streetlight", "noise_complaint",
                       "waste_disposal", "water_supply"]
        disaster_types = ["earthquake", "flood", "fire", "gas_leak"]
        severities = ["1_minor", "2_moderate", "3_significant", "4_severe"]

        if data_type == "complaints":
            return {
                "event_time": datetime.now().isoformat(),
                "citizen_id": f"MASKED_{random.randint(10000, 99999)}",
                "issue_type": random.choice(issue_types),
                "region_code": random.choice(regions),
                "content_length": random.randint(50, 500),
                "priority": random.choice(["low", "medium", "high"]),
            }
        elif data_type == "disasters":
            return {
                "alert_id": f"DST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}",
                "event_time": datetime.now().isoformat(),
                "disaster_type": random.choice(disaster_types),
                "severity": random.choice(severities),
                "location": {
                    "latitude": round(35.0 + random.random() * 3, 6),
                    "longitude": round(126.0 + random.random() * 3, 6),
                },
            }
        elif data_type == "traffic":
            return {
                "sensor_id": f"SENSOR_{random.randint(100, 999):04d}",
                "timestamp": datetime.now().isoformat(),
                "road_section": f"SEC_{random.randint(1, 100):03d}",
                "speed": random.randint(10, 120),
                "volume": random.randint(100, 3000),
            }
        else:  # environment
            return {
                "station_id": f"STN_{random.randint(100, 200):03d}",
                "measured_at": datetime.now().isoformat(),
                "pm25": random.randint(10, 150),
                "pm10": random.randint(20, 200),
                "o3": round(random.uniform(0.01, 0.1), 4),
            }

    def demo_producer(self, count: int = 5):
        """프로듀서 데모"""
        print("\n[Kafka 프로듀서 데모]")
        print("-" * 60)

        for topic in self.TOPICS.keys():
            print(f"\n  토픽: {topic}")
            for i in range(count):
                data = self.generate_sample_data(topic)
                message = self.producer.send(topic, data)
                print(f"    [{i+1}] offset={message.offset}, key={data.get('event_time', '')[:19]}")

        print(f"\n  총 전송: {self.producer.sent_count}건")

    def demo_consumer(self):
        """컨슈머 데모"""
        print("\n[Kafka 컨슈머 데모]")
        print("-" * 60)

        self.consumer.subscribe(list(self.TOPICS.keys()))

        messages = self.consumer.poll(max_records=20)

        for topic in self.TOPICS.keys():
            topic_messages = [m for m in messages if m.topic == topic]
            print(f"\n  토픽: {topic} ({len(topic_messages)}건 수신)")
            for msg in topic_messages[:3]:
                value = msg.value
                print(f"    offset={msg.offset}: {list(value.keys())[:3]}...")

    def demo_message_flow(self):
        """메시지 흐름 시각화"""
        print("\n[메시지 흐름 시각화]")
        print("-" * 60)

        flow_diagram = """
  ┌──────────────────────────────────────────────────────────────────┐
  │                      Kafka Message Flow                          │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                  │
  │  [Producer]                                                      │
  │      │                                                           │
  │      │ send(topic, value)                                        │
  │      ▼                                                           │
  │  ┌────────────────────────────────────────────────────────────┐ │
  │  │                    Kafka Broker                            │ │
  │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │ │
  │  │  │  complaints  │ │  disasters   │ │   traffic    │ ...   │ │
  │  │  │  ┌─┬─┬─┐    │ │  ┌─┬─┐      │ │  ┌─┬─┬─┬─┬─┐│        │ │
  │  │  │  │P0│P1│P2│   │ │  │P0│P1│     │ │  │P0│..│P5││        │ │
  │  │  │  └─┴─┴─┘    │ │  └─┴─┘      │ │  └─┴─┴─┴─┴─┘│        │ │
  │  │  └──────────────┘ └──────────────┘ └──────────────┘       │ │
  │  └────────────────────────────────────────────────────────────┘ │
  │      │                                                           │
  │      │ poll()                                                    │
  │      ▼                                                           │
  │  [Consumer Group: public-data-processor]                         │
  │      Consumer 1 ─── P0 (complaints)                              │
  │      Consumer 2 ─── P1 (complaints)                              │
  │      Consumer 3 ─── P2 (complaints)                              │
  │                                                                  │
  └──────────────────────────────────────────────────────────────────┘
"""
        print(flow_diagram)

    def print_producer_config(self):
        """프로듀서 설정 출력"""
        print("\n[Kafka 프로듀서 권장 설정 (공공 영역)]")
        print("-" * 60)

        config = """
  # 데이터 손실 방지
  acks: all                              # 모든 복제본 확인
  enable.idempotence: true               # 중복 전송 방지
  max.in.flight.requests.per.connection: 5  # 순서 보장

  # 성능 최적화
  batch.size: 16384                      # 배치 크기
  linger.ms: 10                          # 배치 대기 시간
  compression.type: snappy               # 압축

  # 재시도
  retries: 3                             # 재시도 횟수
  retry.backoff.ms: 100                  # 재시도 간격

  # 보안 (프로덕션)
  security.protocol: SSL                 # 암호화
  ssl.endpoint.identification.algorithm: https
"""
        print(config)

    def print_consumer_config(self):
        """컨슈머 설정 출력"""
        print("\n[Kafka 컨슈머 권장 설정 (공공 영역)]")
        print("-" * 60)

        config = """
  # 오프셋 관리
  auto.offset.reset: earliest            # 처음부터 읽기
  enable.auto.commit: false              # 수동 커밋 (정확성)
  max.poll.records: 500                  # 배치 크기

  # 세션 관리
  session.timeout.ms: 30000              # 세션 타임아웃
  heartbeat.interval.ms: 10000           # 하트비트 간격
  max.poll.interval.ms: 300000           # 폴링 간격

  # 격리 수준
  isolation.level: read_committed        # 커밋된 메시지만

  # 보안 (프로덕션)
  security.protocol: SSL
  group.id: public-data-processor
"""
        print(config)

    def run_demo(self):
        """전체 데모 실행"""
        print("=" * 70)
        print("Kafka 프로듀서/컨슈머 시뮬레이션 데모")
        print("=" * 70)

        self.setup_topics()
        self.demo_producer(count=3)
        self.demo_consumer()
        self.demo_message_flow()
        self.print_producer_config()
        self.print_consumer_config()

        print("\n[Docker 환경에서 실제 Kafka 사용 시]")
        print("-" * 60)
        print("""
  # 1. Docker Compose 실행
  docker-compose up -d

  # 2. Kafka 토픽 생성
  docker exec kafka kafka-topics --create \\
    --topic complaints \\
    --bootstrap-server localhost:9092 \\
    --partitions 3 \\
    --replication-factor 1

  # 3. 메시지 전송 테스트
  docker exec -it kafka kafka-console-producer \\
    --topic complaints \\
    --bootstrap-server localhost:9092

  # 4. 메시지 수신 테스트
  docker exec -it kafka kafka-console-consumer \\
    --topic complaints \\
    --bootstrap-server localhost:9092 \\
    --from-beginning

  # 5. Kafka UI 접속
  http://localhost:8080
""")


def demo():
    """데모 실행"""
    kafka_demo = PublicDataKafkaDemo()
    kafka_demo.run_demo()


if __name__ == "__main__":
    demo()
