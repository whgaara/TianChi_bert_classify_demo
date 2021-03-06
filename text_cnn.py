from torch.nn import functional as F
import os
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

import torch.nn as nn
from torch.optim import Adam
from torch.utils.data import DataLoader
from bert.data.classify_dataset import *


class textCNN(nn.Module):
    def __init__(self, class_num):
        super(textCNN, self).__init__()
        ci = 1  # input chanel size
        kernel_num = 100
        kernel_size = [2, 3, 4, 5]
        vocab_size = VocabSize
        embed_dim = 256
        dropout = 0.1
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=1)
        self.conv11 = nn.Conv2d(ci, kernel_num, (kernel_size[0], embed_dim))
        self.conv12 = nn.Conv2d(ci, kernel_num, (kernel_size[1], embed_dim))
        self.conv13 = nn.Conv2d(ci, kernel_num, (kernel_size[2], embed_dim))
        self.conv14 = nn.Conv2d(ci, kernel_num, (kernel_size[3], embed_dim))
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(len(kernel_size) * kernel_num, class_num)

    def init_embed(self, embed_matrix):
        self.embed.weight = nn.Parameter(torch.Tensor(embed_matrix))

    @staticmethod
    def conv_and_pool(x, conv):
        # x: (batch, 1, sentence_length,  )
        x = conv(x)
        # x: (batch, kernel_num, H_out, 1)
        x = F.relu(x.squeeze(3))
        # x: (batch, kernel_num, H_out)
        x = F.max_pool1d(x, x.size(2)).squeeze(2)
        #  (batch, kernel_num)
        return x

    def forward(self, x):
        # x: (batch, sentence_length)
        x = self.embed(x)
        # x: (batch, sentence_length, embed_dim)
        # TODO init embed matrix with pre-trained
        x = x.unsqueeze(1)
        # x: (batch, 1, sentence_length, embed_dim)
        x1 = self.conv_and_pool(x, self.conv11)  # (batch, kernel_num)
        x2 = self.conv_and_pool(x, self.conv12)  # (batch, kernel_num)
        x3 = self.conv_and_pool(x, self.conv13)  # (batch, kernel_num)
        x4 = self.conv_and_pool(x, self.conv14)  # (batch, kernel_num)
        x = torch.cat((x1, x2, x3, x4), 1)  # (batch, 3 * kernel_num)
        x = self.dropout(x)
        logit = F.log_softmax(self.fc1(x), dim=1)
        return logit

    def init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                m.weight.data.normal_(0, 0.01)
                m.bias.data.zero_()


if __name__ == '__main__':
    onehot_type = False
    labelcount = int(open(Assistant, 'r', encoding='utf-8').readline().split(',')[1])
    model = textCNN(labelcount).to(device)

    testset = BertTestSetHead512(EDemoPath)
    dataset = BertDataSetHead512(TDemoPath)
    dataloader = DataLoader(dataset=dataset, batch_size=BatchSize, shuffle=True, drop_last=False)

    optim = Adam(model.parameters(), lr=LearningRate)
    criterion = nn.CrossEntropyLoss().to(device)

    for epoch in range(Epochs):
        # train
        model.train()
        data_iter = tqdm(enumerate(dataloader),
                         desc='EP_%s:%d' % ('train', epoch),
                         total=len(dataloader),
                         bar_format='{l_bar}{r_bar}')
        print_loss = 0.0
        for i, data in data_iter:
            data = {k: v.to(device) for k, v in data.items()}
            input_token = data['input_token_ids']
            segment_ids = data['segment_ids']
            label = data['token_ids_labels']
            output = model(input_token)
            mask_loss = criterion(output, label)
            print_loss = mask_loss.item()
            optim.zero_grad()
            mask_loss.backward()
            optim.step()
        print('EP_%d mask loss:%s' % (epoch, print_loss))

        # save
        output_path = PretrainPath + '.ep%d' % epoch
        torch.save(model.cpu(), output_path)
        model.to(device)
        print('EP:%d Model Saved on:%s' % (epoch, output_path))

        # test
        with torch.no_grad():
            model.eval()
            test_count = 0
            accuracy_count = 0
            for test_data in testset:
                test_count += 1
                input_token = test_data['input_token_ids'].unsqueeze(0).to(device)
                segment_ids = test_data['segment_ids'].unsqueeze(0).to(device)
                label = test_data['token_ids_labels'].tolist()
                output = model(input_token)
                output_tensor = torch.nn.Softmax(dim=-1)(output)
                output_topk = torch.topk(output_tensor, 1).indices.squeeze(0).tolist()

                # 累计数值
                if label == output_topk[0]:
                    accuracy_count += 1

            if test_count:
                acc_rate = float(accuracy_count) / float(test_count)
                acc_rate = round(acc_rate, 2)
                print('新闻类别判断正确率：%s' % acc_rate)