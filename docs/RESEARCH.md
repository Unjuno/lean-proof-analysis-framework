# Related work and initial research position

This is a selection of relevant work, **not a claim of novelty** or an exhaustive literature review.

| Area | Reference | Reusable idea |
|---|---|---|
| Extraction/premise retrieval | Yang et al., **LeanDojo**, NeurIPS 2023, [arXiv:2306.15626](https://arxiv.org/abs/2306.15626) | Reproducible theorem information and premise retrieval for Lean |
| Proof pattern discovery | Komendantskaya et al., **Proof Mining with Statistical Methods (ML4PG)**, [arXiv:1402.0081](https://arxiv.org/abs/1402.0081) | Discover recurring patterns beyond exact syntax |
| Structure-based retrieval | **Tree-Based Premise Selection for Lean4**, NeurIPS 2025, [proceedings](https://proceedings.neurips.cc/paper_files/paper/2025/hash/2ee86e3e9315027920ff2f205f4c3b3a-Abstract-Conference.html) | Compare statement trees, term constants, and structures |
| Explanation | Hattori et al., INLG 2025, [ACL Anthology](https://aclanthology.org/2025.inlg-main.23/) | Incremental and hierarchy-aware natural-language explanation |
| Target corpus | [leanprover-community/riemann-hypothesis](https://github.com/leanprover-community/riemann-hypothesis) | First large-case-study repository, independently pinned |

## Research gap to test

Existing work provides many building blocks. We will test whether a **shared, traceable, human-and-agent usable framework** reduces reviewer navigation effort while preserving access to the exact formal source and clearly conveying unknowns.

Potential contribution: careful integration, information provenance, reproducible evaluation and task-grounded human measurements. It has **not yet** been demonstrated that this combination is novel or produces an improvement.

## Fields connected

- Formal logic and proof engineering: elaborated declarations and proof dependencies.
- Software engineering and graph analysis: reproducible builds, modularization, dependency navigation.
- Information retrieval and ML: candidate selection, reranking, structural similarity.
- Human–computer interaction: whether information structure assists actual review tasks.
