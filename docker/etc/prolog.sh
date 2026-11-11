#!/bin/bash
# HAKUSAN の $JOBDIR を模したテスト用 Prolog（root で計算ノード上で実行）
mkdir -p "/JOBs/$SLURM_JOB_ID" && chown "$SLURM_JOB_USER" "/JOBs/$SLURM_JOB_ID" && chmod 700 "/JOBs/$SLURM_JOB_ID"
