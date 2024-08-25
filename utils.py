from os.path import join
from functools import partial

import mindspore




class Trainer(object):
    def __init__(self, optimizer, model, train_loader,
                 val_loader, save_dir, clip,
                 print_freq, ckpt_freq, patience, epoch,copy=False):
        self.optimizer = optimizer
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.save_dir = save_dir

        self.clip = clip
        self.print_freq = print_freq
        self.ckpt_freq = ckpt_freq
        self.patience = patience
        self.model_is_copy = copy

        self.step = 0
        self.cur_epoch=1
        self.epoch = epoch

        self.current_p = 0
        self.best_val = 1e18
        self.current_val_loss = 1e18

    def validate(self):
        # cal val loss
        print('start val')
        self.model.set_train(False)
        val_total_loss = 0.0
        val_batch=100
        for i in range(val_batch):
        #for srcs, targets in self.val_loader:
            srcs, targets = self.val_loader.next_batch()
            src, src_lens, tgt = srcs
            # src, src_lens, tgt = srcs

            logit = self.model(src, src_lens, tgt)
            val_loss = self.cal_loss(logit, targets)
            val_total_loss += val_loss.item()

        avg_loss = val_total_loss / val_batch
        print("Epoch {}, validation average loss: {:.4f}".format(
            self.cur_epoch, avg_loss
        ))
        self.current_val_loss = avg_loss
        return avg_loss

    def checkpoint(self):
        save_dict = {}
        # name = 'ckpt-{:6f}-{}e-{}s'.format(
        #     self.current_val_loss, self.epoch, self.step
        # )
        name= 'ckpt-{}e-{}s'.format( self.cur_epoch, self.step
        )
        # save_dict['state_dict'] = self.model.state_dict()
        # save_dict['optimizer'] = self.optimizer.state_dict()
        mindspore.save_checkpoint(self.model, join(self.save_dir, name))

    def log_info(self, losses):
        total_step = self.train_loader.tot_batch
        print("Epoch {}, step:{}/{} {:.2f}%, Loss:{:.4f}".format(
            self.cur_epoch, self.step, total_step,
            100 * self.step / total_step,
            losses / self.print_freq
            ))

    def check_stop(self, val_loss):
        if val_loss < self.best_val:
            self.best_val = val_loss
            self.checkpoint()
            self.current_p = 0
        else:
            self.current_p += 1
        return self.current_p >= self.patience

    def forward(self,srcs, targets):
        src, src_lens, tgt = srcs
        logits = self.model(src, src_lens, tgt)

        #loss = self.cal_loss(logits, targets)
        pad_idx=0
        mask = (targets != pad_idx)
        targets = targets.masked_select(mask)
        logits = logits.masked_select(
            mask.unsqueeze(2).expand_as(logits)
        ).view(-1, logits.shape[2])
        loss = mindspore.ops.nll_loss(logits, targets)

        return loss

    def clip_by_norm(self,clip_norm, t, axis=None):


        # 计算L2-norm
        t2 = t * t
        l2sum = t2.sum(axis=axis, keepdims=True)
        pred = l2sum > 0
        l2sum_safe = mindspore.ops.select(pred, l2sum,  mindspore.ops.ones_like(l2sum))
        l2norm =  mindspore.ops.select(pred,  mindspore.ops.sqrt(l2sum_safe), l2sum)
        intermediate = t * clip_norm
        cond = l2norm > clip_norm
        t_clip =  mindspore.ops.identity(intermediate /  mindspore.ops.select(cond, l2norm, clip_norm))
        return t_clip


    #@mindspore.jit
    def train_step(self, srcs, targets):
        loss, grads = self.grad_fn(srcs, targets)
        #grads = map(partial(self.clip_by_norm, self.clip), grads)
        #grads=self.clip_by_norm(self.clip,grads)
        #grads=mindspore.ops.clip_by_norm(grads,self.clip)
        self.optimizer(grads)
        self.step += 1



        #loss.backward()
        #clip_grad_norm_(self.model.parameters(), self.clip)
        # self.optimizer.step()
        # self.optimizer.zero_grad()
        return loss.item()

    def train(self):
        self.grad_fn = mindspore.ops.value_and_grad(self.forward, None, self.optimizer.parameters)
        while True:
            self.model.set_train()
            losses = 0.0
            for i in range(self.train_loader.tot_batch):
            #for srcs, targets in self.train_loader:
                srcs, targets = self.train_loader.next_batch()
                step_loss = self.train_step(srcs, targets)
                losses += step_loss

                if self.step % self.print_freq == 0:
                    #log message
                    self.log_info(losses)
                    losses = 0.0
                    #val_loss = self.validate()
                # if self.step % self.ckpt_freq == 0:
                #     #save current model
                #     self.checkpoint()


            self.step = 0
            # get val loss and
            # check whether to early stop
            val_loss = self.validate()
            self.checkpoint()
            if self.check_stop(val_loss):
                print("Finished Training!")
                self.checkpoint()
                break
            self.cur_epoch += 1
            if self.cur_epoch>self.epoch:
                break

    def cal_loss(self, logits, targets, pad_idx=0):
        mask = (targets != pad_idx)
        targets = targets.masked_select(mask)
        logits = logits.masked_select(
            mask.unsqueeze(2).expand_as(logits)
        ).view(-1, logits.shape[2])


        loss = mindspore.ops.nll_loss(logits, targets)
        return loss
