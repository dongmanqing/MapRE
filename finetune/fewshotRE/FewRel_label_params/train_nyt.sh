export CUDA_VISIBLE_DEVICES=2

python train_demo.py --train train_nyt --val val_nyt --test test_nyt --train_iter 1000 --val_iter 200 --test_iter 1000 \
	--trainN 5 --N 5 --K 5 --Q 1 --max_length 200 \
	--model proto --encoder bert --hidden_size 768 --val_step 200 \
  --batch_size 4 --alpha 0.1 \
	--path ../../../pretrain_relation/ckpt/ckpt_cp/ckpt_of_step_11000

