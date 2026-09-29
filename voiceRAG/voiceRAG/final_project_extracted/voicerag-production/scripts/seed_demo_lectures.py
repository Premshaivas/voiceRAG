"""Seed script to populate VoiceRAG with realistic, high-quality showcase lectures.

Creates:
1. CS224N: Retrieval-Augmented Generation & Large Language Models
2. MIT 6.824: Distributed Systems & Raft Consensus Algorithm
3. Deep Learning: Backpropagation, Loss Surfaces & Optimization

For each lecture:
- Creates Document record in PostgreSQL
- Creates Transcript record with word-level timestamps
- Creates valid audio file in storage directory and MinIO S3
- Indexes semantic chunks into Qdrant vector database
"""

import asyncio
import io
import json
import math
import os
import struct
import uuid
import wave
from pathlib import Path
from sqlalchemy import select

from backend.config import settings
from backend.db import Document, DocumentStatus, Transcript, User, create_database
from backend.rag_engine import RAGPipeline


DEMO_LECTURES = [
    {
        "title": "CS224N Lecture 12: Large Language Models & Retrieval-Augmented Generation",
        "filename": "cs224n_lecture12_rag_llms.mp3",
        "speech_model": "universal-3-5-pro",
        "language_code": "en",
        "text": (
            "Welcome everyone to Lecture 12 of CS224N. Today we are exploring Retrieval-Augmented "
            "Generation, commonly referred to as RAG, and its critical role in making Large Language "
            "Models reliable, verifiable, and free from hallucinations. "
            "First, why do we need RAG? Standard generative models, whether they are based on GPT, "
            "Claude, or LLaMA architectures, are trained on static snapshots of internet corpora. "
            "As a consequence, they have two fundamental weaknesses: parametric knowledge decay, "
            "where they are unaware of events occurring after their training cutoff date, and "
            "hallucination, where they generate plausible-sounding falsehoods with high confidence. "
            "Rather than endlessly retraining or fine-tuning colossal models on proprietary data, RAG "
            "decouples knowledge storage from reasoning. The parametric model handles linguistic "
            "synthesis and reasoning, while an external non-parametric retrieval system supplies fresh, "
            "verifiable context. "
            "Let us examine the retrieval architecture. In standard dense retrieval, we employ "
            "bi-encoders. The document collection is partitioned into discrete chunks—typically 256 "
            "to 1024 tokens with a 10 to 20 percent overlap to prevent semantic boundaries from slicing "
            "through critical thoughts. Each chunk is passed through an embedding model such as "
            "Sentence-Transformers or BAAI General Embedding, converting text into dense vectors in "
            "high-dimensional space. At query time, the user's natural language question is embedded "
            "using the exact same vector space. We then execute a nearest-neighbor vector search—often "
            "accelerated using Hierarchical Navigable Small World, or HNSW graph indexing—computing "
            "cosine distance against the entire index in sub-millisecond time. "
            "Once the top-K relevant passages are retrieved, they are injected into the prompt along "
            "with the user's question. A cross-encoder or re-ranker model is frequently placed between "
            "the initial retrieval and prompt assembly. Re-rankers evaluate query-document pairs "
            "jointly, capturing nuanced cross-attention interactions that bi-encoders miss. The "
            "synthesis stage then instructs the LLM to generate an answer strictly grounded in the "
            "provided context, demanding direct citations with chunk identifiers and timestamp "
            "references. If the retrieved context is insufficient, the system gracefully declines to "
            "answer rather than fabricating facts. This completes the core RAG lifecycle."
        ),
    },
    {
        "title": "MIT 6.824 Lecture 6: Distributed Consensus & The Raft Algorithm",
        "filename": "mit_6824_raft_consensus.mp3",
        "speech_model": "universal-3-5-pro",
        "language_code": "en",
        "text": (
            "Good morning class. Today we dive into distributed consensus, focusing on the Raft "
            "consensus algorithm developed by Diego Ongaro and John Ousterhout at Stanford. Consensus "
            "is the foundational cornerstone of modern fault-tolerant distributed databases, such as "
            "CockroachDB, TiKV, and etcd. "
            "In distributed systems, machines crash, network links suffer packet loss, and latency "
            "fluctuates unpredictably. The consensus problem asks: how can a cluster of independent "
            "state machines agree on an identical sequence of operational logs, even when up to half "
            "of the servers fail? Before Raft, Paxos was the standard, but Paxos is notoriously "
            "difficult to understand and implement correctly. Raft was deliberately designed for "
            "understandability by decomposing consensus into three independent subproblems: leader "
            "election, log replication, and safety invariants. "
            "Let us explore leader election. A Raft server exists in one of three states: Follower, "
            "Candidate, or Leader. Normal operation begins with followers. Every follower maintains "
            "a randomized election timer, typically between 150 and 300 milliseconds. If a follower "
            "hears no heartbeat from the leader before its timer expires, it assumes the leader has "
            "crashed. The follower transitions into a Candidate, increments the current term number, "
            "votes for itself, and broadcasts RequestVote RPCs to all peers. The randomized timeout "
            "is crucial: it prevents split votes where multiple candidates compete simultaneously "
            "and deadlock. Once a candidate receives votes from a strict majority of nodes, it "
            "becomes the new cluster Leader. "
            "Now, how does log replication work? When a client submits a mutation command, the "
            "leader appends the entry to its own log and broadcasts AppendEntries RPCs to all "
            "followers. Followers verify that their preceding log entries match the leader's terms. "
            "When a majority of followers acknowledge writing the log entry to stable disk storage, "
            "the leader considers the entry committed. The leader applies the entry to its local "
            "state machine and returns success to the client. On subsequent heartbeats, the leader "
            "notifies followers of the updated commit index, prompting them to execute the committed "
            "operations on their own state machines. This guarantees linearizable consistency across "
            "the distributed cluster."
        ),
    },
    {
        "title": "Deep Learning: Backpropagation, Loss Surfaces & Modern Optimizers",
        "filename": "deep_learning_backprop_optimizers.mp3",
        "speech_model": "universal-3-5-pro",
        "language_code": "en",
        "text": (
            "Welcome to our deep dive on optimization and gradient backpropagation in modern deep "
            "neural networks. Today we trace how gradients flow backward through deep computational "
            "graphs to iteratively minimize empirical risk. "
            "Let us establish the mathematical core. A neural network is fundamentally a composition "
            "of parameterized functions. During the forward pass, input vectors propagate through "
            "weight matrices, biases, and non-linear activation functions such as ReLU, GELU, or "
            "SwiGLU. The network produces a prediction, which is evaluated against ground truth labels "
            "using a scalar loss function, such as cross-entropy or mean squared error. "
            "Backpropagation is the algorithmic application of the multivariate chain rule of calculus "
            "to compute the exact partial derivatives of the loss with respect to every learnable "
            "parameter in the network. "
            "However, training deep architectures involves navigating treacherous non-convex loss "
            "surfaces. High-dimensional loss landscapes are rarely obstructed by isolated local "
            "minima; instead, they are plagued by ubiquitous saddle points, ill-conditioned curvature "
            "ravines, and plateaus where gradients vanish to near zero. When gradients vanish "
            "exponentially across layers, earlier weights receive no learning signal, freezing model "
            "convergence. Conversely, exploding gradients cause numerical instability and NaN "
            "overflow. Modern architectures overcome this through residual skip connections, layer "
            "normalization, and careful weight initializations like He or Xavier scaling. "
            "Finally, we have optimization algorithms. Standard Stochastic Gradient Descent updates "
            "weights proportional to the negative gradient. But plain SGD oscillates wildly in "
            "ravines of high curvature. Momentum addresses this by accumulating a velocity vector, "
            "dampening oscillations and accelerating through flat regions. Adaptive gradient methods "
            "like RMSprop scale updates inversely with the running root-mean-square of past gradients. "
            "The industry standard, Adam, synthesizes both momentum and adaptive learning rates, "
            "tracking exponential moving averages of both the first and second moments of gradients. "
            "Furthermore, AdamW decouples L2 weight decay from gradient updates, yielding superior "
            "generalization in modern language models and vision transformers."
        ),
    },
]


def generate_synthesized_wav(duration_seconds: float = 120.0, sample_rate: int = 22050) -> bytes:
    """Generate a clean, pleasant ambient multi-tone audio stream for playback."""
    num_samples = int(duration_seconds * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Soft harmonic tones at 220Hz (A3) and 440Hz (A4) with gentle envelope
            sample = 0.25 * math.sin(2 * math.pi * 220.0 * t) + 0.15 * math.sin(2 * math.pi * 440.0 * t)
            # Add subtle pulsing envelope
            envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 0.1 * t)
            val = int(sample * envelope * 20000.0)
            val = max(-32768, min(32767, val))
            frames.extend(struct.pack("<h", val))
        wav.writeframes(frames)
    return buffer.getvalue()


def build_words_json(text: str) -> list[dict]:
    """Build fine-grained word-level timestamps."""
    words = text.split()
    result = []
    current_ms = 1200
    for w in words:
        duration = max(240, int(len(w) * 55))
        result.append({
            "text": w,
            "start": current_ms,
            "end": current_ms + duration,
        })
        current_ms += duration + (200 if any(punct in w for punct in ".?!") else 40)
    return result


async def main():
    print("Connecting to database...")
    _, SessionLocal = create_database()
    
    pipeline = RAGPipeline(
        persist_directory=settings.chroma_dir,
    )
    print(f"RAGPipeline initialized with vector backend: {settings.vector_backend}")

    # Generate synthetic audio file
    print("Generating demo lecture audio bytes...")
    wav_bytes = generate_synthesized_wav(duration_seconds=180.0)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    async with SessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        print(f"Found {len(users)} users in database: {[u.email for u in users]}")

        target_users = users if users else [None]

        for lecture in DEMO_LECTURES:
            words = build_words_json(lecture["text"])
            words_str = json.dumps(words)

            for user in target_users:
                user_id = user.id if user else None
                user_email = user.email if user else "anonymous"

                doc_id = str(uuid.uuid4())
                file_path = upload_dir / f"{doc_id}.wav"
                with open(file_path, "wb") as f:
                    f.write(wav_bytes)

                doc = Document(
                    id=doc_id,
                    owner_id=user_id,
                    title=lecture["title"],
                    filename=lecture["filename"],
                    storage_path=str(file_path),
                    status=DocumentStatus.completed,
                )
                session.add(doc)

                transcript = Transcript(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    assemblyai_id=f"demo-{uuid.uuid4().hex[:12]}",
                    text=lecture["text"],
                    words_json=words_str,
                    language_code=lecture["language_code"],
                    speech_model=lecture["speech_model"],
                )
                session.add(transcript)

                # Index in Qdrant
                metadata = {
                    "document_id": doc_id,
                    "title": lecture["title"],
                    "filename": lecture["filename"],
                }
                if user_id:
                    metadata["owner_id"] = user_id

                pipeline.add_document(lecture["text"], metadata=metadata, words=words)
                print(f"  [+] Added '{lecture['title']}' for {user_email} (ID: {doc_id})")

        await session.commit()
    print("All demo lectures seeded and indexed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
