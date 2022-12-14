import argparse
import json
import os
import random

import numpy as np
import torch
from torch import optim

from fewshot_re_kit.data_loader import get_loader_label, get_loader_pair, get_loader_test, get_loader_test_label, get_loader_unsupervised
from fewshot_re_kit.framework import FewShotREFramework
from fewshot_re_kit.sentence_encoder import CNNSentenceEncoder, BERTSentenceEncoder, BERTPAIRSentenceEncoder, \
    RobertaSentenceEncoder, RobertaPAIRSentenceEncoder
from models.d import Discriminator
from models.gnn import GNN
from models.metanet import MetaNet
from models.pair import Pair
from models.proto import Proto
from models.siamese import Siamese
from models.snail import SNAIL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', default='train_wiki',
                        help='train file')
    parser.add_argument('--val', default='val_wiki',
                        help='val file')
    parser.add_argument('--test', default='val_wiki',
                        help='test file')
    parser.add_argument('--adv', default=None,
                        help='adv file')
    parser.add_argument('--trainN', default=10, type=int,
                        help='N in train')
    parser.add_argument('--N', default=5, type=int,
                        help='N way')
    parser.add_argument('--K', default=5, type=int,
                        help='K shot')
    parser.add_argument('--Q', default=5, type=int,
                        help='Num of query per class')
    parser.add_argument('--batch_size', default=4, type=int,
                        help='batch size')
    parser.add_argument('--train_iter', default=10000, type=int,
                        help='num of iters in training')
    parser.add_argument('--val_iter', default=1000, type=int,
                        help='num of iters in validation')
    parser.add_argument('--test_iter', default=10000, type=int,
                        help='num of iters in testing')
    parser.add_argument('--val_step', default=1000, type=int,
                        help='val after training how many iters')
    parser.add_argument('--model', default='proto',
                        help='model name')
    parser.add_argument('--encoder', default='cnn',
                        help='encoder: cnn or bert or roberta')
    parser.add_argument('--max_length', default=128, type=int,
                        help='max length')
    parser.add_argument('--lr', default=3e-5, type=float,
                        help='learning rate')
    parser.add_argument('--weight_decay', default=1e-5, type=float,
                        help='weight decay')
    parser.add_argument('--dropout', default=0.0, type=float,
                        help='dropout rate')
    parser.add_argument('--na_rate', default=0, type=int,
                        help='NA rate (NA = Q * na_rate)')
    parser.add_argument('--grad_iter', default=1, type=int,
                        help='accumulate gradient every x iterations')
    parser.add_argument('--optim', default='adamw',
                        help='sgd / adam / adamw')
    parser.add_argument('--hidden_size', default=230, type=int,
                        help='hidden size')
    parser.add_argument('--load_ckpt', default=None,
                        help='load ckpt')
    parser.add_argument('--save_ckpt', default=None,
                        help='save ckpt')
    parser.add_argument('--fp16', action='store_true',
                        help='use nvidia apex fp16')
    parser.add_argument('--only_test', action='store_true',
                        help='only test')
    parser.add_argument('--pair', action='store_true',
                        help='use pair model')
    parser.add_argument('--pretrain_ckpt', default='bert-base-uncased',
                        help='bert / roberta pre-trained checkpoint')
    parser.add_argument('--seed', default=42, type=int,
                        help='seed')
    parser.add_argument('--path', default='../../../CP',
                        help='path to ckpt')
    parser.add_argument('--mode', default="CM",
                        help='mode {CM, OC, OM}')
    parser.add_argument('--alpha', default=0.5, type=float)

    opt = parser.parse_args()
    random.seed(opt.seed)
    np.random.seed(opt.seed)
    torch.manual_seed(opt.seed)
    torch.cuda.manual_seed_all(opt.seed)
    trainN = opt.trainN
    N = opt.N
    K = opt.K
    Q = opt.Q
    batch_size = opt.batch_size
    model_name = opt.model
    encoder_name = opt.encoder
    max_length = opt.max_length

    print("{}-way-{}-shot Few-Shot Relation Classification".format(N, K))
    print("model: {}".format(model_name))
    print("encoder: {}".format(encoder_name))
    print("max_length: {}".format(max_length))

    if encoder_name == 'cnn':
        try:
            glove_mat = np.load('./pretrain/glove/glove_mat.npy')
            glove_word2id = json.load(open('./pretrain/glove/glove_word2id.json'))
        except:
            raise Exception("Cannot find glove files. Run glove/download_glove.sh to download glove files.")
        sentence_encoder = CNNSentenceEncoder(
            glove_mat,
            glove_word2id,
            max_length)
    elif encoder_name == 'bert':
        pretrain_ckpt = opt.pretrain_ckpt or 'bert-base-uncased'
        if opt.pair:
            sentence_encoder = BERTPAIRSentenceEncoder(
                pretrain_ckpt,
                max_length)
        else:
            sentence_encoder = BERTSentenceEncoder(
                pretrain_ckpt,
                max_length,
                opt.path,
                opt.mode)
    elif encoder_name == 'roberta':
        pretrain_ckpt = opt.pretrain_ckpt or 'roberta-base'
        if opt.pair:
            sentence_encoder = RobertaPAIRSentenceEncoder(
                pretrain_ckpt,
                max_length)
        else:
            sentence_encoder = RobertaSentenceEncoder(
                pretrain_ckpt,
                max_length)
    else:
        raise NotImplementedError

    if opt.pair:
        train_data_loader = get_loader_pair(opt.train, sentence_encoder,
                                            N=trainN, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size,
                                            encoder_name=encoder_name)
        val_data_loader = get_loader_pair(opt.val, sentence_encoder,
                                          N=N, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size,
                                          encoder_name=encoder_name)
        test_data_loader = get_loader_pair(opt.test, sentence_encoder,
                                           N=N, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size,
                                           encoder_name=encoder_name)
    else:
        train_data_loader = get_loader_label(opt.train, 'data/pid2name.json', sentence_encoder,
                                             tokenizer_name=opt.pretrain_ckpt,
                                             N=trainN, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size)
        val_data_loader = get_loader_label(opt.val, 'data/pid2name.json', sentence_encoder,
                                           tokenizer_name=opt.pretrain_ckpt,
                                           N=N, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size)
        if opt.test != 'test_nyt' and not opt.test.startswith('val_'):
            test_data_loader = get_loader_test_label(opt.test, 'data/pid2name.json', sentence_encoder,
                                                     tokenizer_name=opt.pretrain_ckpt,
                                               N=N, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size)
        else:
            test_data_loader = get_loader_label(opt.test, 'data/pid2name.json', sentence_encoder,
                                           tokenizer_name=opt.pretrain_ckpt,
                                           N=N, K=K, Q=1, na_rate=opt.na_rate, batch_size=batch_size)
            pass
        if opt.adv:
            adv_data_loader = get_loader_unsupervised(opt.adv, sentence_encoder,
                                                      N=trainN, K=K, Q=Q, na_rate=opt.na_rate, batch_size=batch_size)

    if opt.optim == 'sgd':
        pytorch_optim = optim.SGD
    elif opt.optim == 'adam':
        pytorch_optim = optim.Adam
    elif opt.optim == 'adamw':
        from transformers import AdamW
        pytorch_optim = AdamW
    else:
        raise NotImplementedError
    if opt.adv:
        d = Discriminator(opt.hidden_size)
        framework = FewShotREFramework(train_data_loader, val_data_loader, test_data_loader, adv_data_loader,
                                       adv=opt.adv, d=d)
    else:
        framework = FewShotREFramework(train_data_loader, val_data_loader, test_data_loader)

    prefix = '-'.join([model_name, encoder_name, opt.train, opt.val, str(N), str(K)])
    if opt.adv is not None:
        prefix += '-adv_' + opt.adv
    if opt.na_rate != 0:
        prefix += '-na{}'.format(opt.na_rate)

    if model_name == 'proto':
        model = Proto(sentence_encoder, opt.pretrain_ckpt, opt.path, hidden_size=opt.hidden_size, alpha=opt.alpha)
        prefix += '-alpha_{}'.format(opt.alpha)
    elif model_name == 'gnn':
        model = GNN(sentence_encoder, N)
    elif model_name == 'snail':
        print("HINT: SNAIL works only in PyTorch 0.3.1")
        model = SNAIL(sentence_encoder, N, K)
    elif model_name == 'metanet':
        model = MetaNet(N, K, sentence_encoder.embedding, max_length)
    elif model_name == 'siamese':
        model = Siamese(sentence_encoder, hidden_size=opt.hidden_size, dropout=opt.dropout)
    elif model_name == 'pair':
        model = Pair(sentence_encoder, hidden_size=opt.hidden_size)
    else:
        raise NotImplementedError

    if not os.path.exists('checkpoint'):
        os.mkdir('checkpoint')
    ckpt = 'checkpoint/{}.pth.tar'.format(prefix)
    if opt.save_ckpt:
        ckpt = opt.save_ckpt

    if torch.cuda.is_available():
        model.cuda()

    if not opt.only_test:
        if encoder_name in ['bert', 'roberta']:
            bert_optim = True
        else:
            bert_optim = False

        framework.train(model, prefix, batch_size, trainN, N, K, Q,
                        pytorch_optim=pytorch_optim, load_ckpt=opt.load_ckpt, save_ckpt=ckpt,
                        na_rate=opt.na_rate, val_step=opt.val_step, fp16=opt.fp16, pair=opt.pair,
                        train_iter=opt.train_iter, val_iter=opt.val_iter, bert_optim=bert_optim)
    else:
        ckpt = opt.load_ckpt

    if opt.test == 'test_nyt':
        framework.eval(model, batch_size, N, K, 1, opt.test_iter, ckpt=ckpt)
    elif opt.test.startswith('val_'):
        framework.eval(model, batch_size, N, K, 1, opt.test_iter, ckpt=ckpt)
    else:
        res = framework.test(model, batch_size, N, K, 1, na_rate=opt.na_rate, ckpt=ckpt, pair=opt.pair)
        print(res)
        os.makedirs(opt.test[:9], exist_ok=True)
        with open('{}/pred-{}-{}.json'.format(opt.test[:9], N, K), 'w') as f:
            json.dump(res, f)


if __name__ == "__main__":
    main()
