"""Reframe archived screenshots without changing their pixels or results."""
from __future__ import annotations
from PIL import Image
from drawing import *


def build(pack,root):
    source=root/'docs/deliveries/2026-10-20-web-redesign/desktop.png'
    wrong=root/'docs/deliveries/2026-10-20-web-rejection-screenshots/wrong-receiver.png'
    fig,ax=pack.canvas(660)
    im=Image.open(source).convert('RGB').crop((135,115,1308,785))
    ax.imshow(im,extent=(30,970,622,85),interpolation='none',aspect='auto',zorder=2)
    ax.set_xlim(0,1000);ax.set_ylim(660,0)
    text(ax,30,30,'实际收发界面',size=20,weight='bold')
    text(ax,30,643,'归档截图：保留方案、身份、消息和运行指标。',size=11,color=MUTED)
    pack.save(fig,'fig-06-04-web','A 组实际收发界面','6.4','6.5',('web_screenshot',),note='原截图裁切；没有修改界面内容。')
    fig,ax=pack.canvas(490)
    text(ax,30,30,'匹配解密与身份错配的实际结果',size=20,weight='bold')
    for x,path,label,color in [(30,source,'双方身份匹配',TEAL),(520,wrong,'接收身份不匹配',BLUE)]:
        im=Image.open(path).convert('RGB').crop((865,245,1300,551))
        text(ax,x,88,label,size=15,weight='bold',color=color)
        ax.imshow(im,extent=(x,x+450,425,109),interpolation='none',aspect='auto',zorder=2)
        ax.set_xlim(0,1000);ax.set_ylim(490,0)
    text(ax,30,466,'来自两次独立操作的界面截图；同一消息与发送者，右侧更换接收者为 Carol。',size=11,color=MUTED)
    pack.save(fig,'fig-06-05-web-results','网页演示的匹配与拒绝结果','6.5','6.5',('web_screenshot','wrong_receiver_screenshot'),note='原截图分别裁切结果区并排排版。')
