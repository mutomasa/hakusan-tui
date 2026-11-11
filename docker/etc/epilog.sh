#!/bin/bash
# ジョブ終了で $JOBDIR を削除（資料 p.50–52 の挙動を模倣）
rm -rf "/JOBs/$SLURM_JOB_ID"
