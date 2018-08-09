from pydub import AudioSegment
from pydub.silence import split_on_silence
from pydub.silence import detect_nonsilent
from pydub.playback import play
import copy
import sys
import threading
import signal
import os
import numpy as np
from multiprocessing import Process, Queue
import matplotlib.pyplot as plt
import matplotlib.animation as animation 
from datetime import datetime
import time


def genSplitFile():
    fileName = sys.argv[1]
    sound = AudioSegment.from_mp3(fileName)
    not_silence_ranges = detect_nonsilent(sound, 350, -45)
    keep_silence = 300

    sys.stdout = open(os.path.splitext(fileName)[0]+".txt", "w")
    for start_i, end_i in not_silence_ranges:
        start_i = max(0, start_i - keep_silence)
        end_i += keep_silence
        print("{0} {1}".format(start_i, end_i))

class Chunks(object):
    def __init__(self):
        self.chunks = []
        self.index = 0
        self.fileName = sys.argv[1]
    
    @property
    def length(self):
        return len(self.chunks)

    def next(self):
        self.index = (self.index+1) % self.length

    def pre(self):
        self.index = (self.index-1) % self.length

    def delete(self):
        del self.chunks[self.index]
        if self.index >= self.length:
            self.index = self.length - 1

    def combine(self):
        if self.index + 1 >= self.length:
            return
        self.chunks[self.index][1] = self.chunks[self.index+1][1]
        del self.chunks[self.index+1]

    def insert(self, middle_time):
        print("start is", self.chunks[self.index][0])
        print("middle is", middle_time)
        end_time = self.chunks[self.index][1]
        print("end is", end_time)
        self.chunks[self.index][1] = middle_time
        self.chunks.insert(self.index+1, [middle_time, end_time])


    def get_section_start(self):
        return self.chunks[self.index][0]

    def get_section_end(self):
        return self.chunks[self.index][1]
    
    def section_start_tweak(self, v):
        self.chunks[self.index][0]+=v

    def section_end_tweak(self, v):
        self.chunks[self.index][1]+=v

    def load(self):
        with open(os.path.splitext(self.fileName)[0]+".txt", "r") as f:
            for i in f:
                i = i.strip()
                if not i:
                    continue
                chunk = i.split(" ")
                chunk = list(map(int, chunk))
                self.chunks.append(chunk)

    def save(self):
        with open(os.path.splitext(self.fileName)[0]+".txt", "w") as f:
            for i in self.chunks:
                f.write("{0} {1}\n".format(i[0], i[1]))
    
    def get_interval(self):
        interval_size = 10
        start = self.get_section_start()
        end = self.get_section_end()
        interval = list(np.arange(start, end, interval_size))
        return list(zip(interval[:-1], interval[1:]))

class PlayProcess(object):
    def __init__(self):
        fileName = sys.argv[1]
        self.sound = AudioSegment.from_mp3(fileName)
        self.progress_start = datetime.now()
        self.line = None
        
    def update(self,data): 
        self.line.set_ydata([20,20]) 
        self.line.set_xdata(data)
        return self.line, 
    def data_gen(self): 
        while True: 
            diff = datetime.now() - self.progress_start 
            yield [self.x_axis[0], self.x_axis[0]+diff.total_seconds()*1000.0]
    def onclick(self, event):
        print('%s click: button=%d, x=%d, y=%d, xdata=%f, ydata=%f' %
            ('double' if event.dblclick else 'single', event.button,
            event.x, event.y, event.xdata, event.ydata))
        print("putting into the queue", int(event.xdata))
        self.queue.put(int(event.xdata))
        

    def draw_wave(self, chunks:Chunks):
        fig = plt.figure() 
        interval = chunks.get_interval()
        loudness = list(map(lambda x: self.sound[x[0]:x[1]].rms, interval))
        max_rms = max(loudness)
        loudness_std = list(map(lambda x: int(x/max_rms*480), loudness))

        self.x_axis = map(lambda x: x[0], interval)
        self.x_axis = list(self.x_axis)
        # print("loudness std is \n", loudness_std)
        # print("x_axis is\n", self.x_axis)
        plt.plot(self.x_axis, loudness_std)
        plt.title("audio wave")
        
        self.line, = plt.plot([0, 0],"r")
        plt.xlim([self.x_axis[0], self.x_axis[-1]])
        plt.ylim([0,500])
        ani = animation.FuncAnimation(fig, self.update, self.data_gen, interval=50)
        fig.canvas.mpl_connect('button_press_event', self.onclick)

        plt.show()
        print("draw wave stop")

    def play_chunks(self, chunks:Chunks, mode, is_draw_wave=False ,queue:Queue=None):
        try:
            os.setsid()
        except:
            pass

        def play_thread():
            while(True):
                self.progress_start = datetime.now()
                play(self.sound[chunks.get_section_start():chunks.get_section_end()])

                if mode == "play_once":
                    chunks.next()
                if mode == "play_loop":
                    pass

        self.queue = queue
        t = threading.Thread(target=play_thread)
        t.setDaemon(False)
        t.start()
        if is_draw_wave:
            self.draw_wave(chunks)

        t.join()


        print('subprocess end')

if __name__ == "__main__":
    mode = "play_loop"

    c = Chunks()
    c.load()
    queue = Queue()
    play_process = PlayProcess()

    t = Process(target=play_process.play_chunks, args=(copy.deepcopy(c),mode))
    t.daemon = False
    t.start()
    lastChunks = None

    def restartProcess(t, is_draw_wave=False):
        try:
            os.killpg(os.getpgid(t.pid), signal.SIGTERM)
        except:
            os.kill(t.pid, signal.SIGTERM)
        t = Process(target=play_process.play_chunks, args=(copy.deepcopy(c),mode,is_draw_wave,queue))
        t.start()
        return t

    def wait_insert_break():
        global t, lastChunks
        while True:
            value = queue.get()
            print("get queue with", value)
            if value==0:
                break
            print("get queue with", value)
            lastChunks = copy.deepcopy(c)
            c.insert(value)
            t = restartProcess(t)
        print("thread exit!")

    insert_thread = threading.Thread(target=wait_insert_break)
    insert_thread.start()

    while(True):
        value = input()
        if value == 'l':
            mode = 'play_loop'
            print('alter to loop mode')
            t = restartProcess(t)
        elif value == 'o':
            mode = 'play_once'
            print('alter to once mode')
            t = restartProcess(t)
        elif value == 'p':
            print('paint the wave')
            t = restartProcess(t, is_draw_wave=True)
        elif value == 'd':
            c.delete()
            print('delete a sentence')
            t = restartProcess(t)
        elif value == 'r':
            if lastChunks:
                c = lastChunks
                print('resume chunks')
            t = restartProcess(t)
        elif value =='c':
            lastChunks = copy.deepcopy(c)
            c.combine()
            print('conbine chunks')
            t = restartProcess(t)
        elif value == 's':
            c.save()
            print('save chunks')
        elif value == 'n':
            c.next()
            t = restartProcess(t)
            print('next sentence')
        elif value.startswith('i'):
            s = value.split()
            if(len(s))!=2:
                print("insert param error")
                continue
            lastChunks = copy.deepcopy(c)
            c.insert(int(s[1]))
            t = restartProcess(t)
            print('insert a new break')
        elif value == 'b':
            c.pre()
            print('previous sentence')
            t = restartProcess(t)
        elif value.startswith('z'):
            s = value.split()
            c.section_start_tweak(int(s[1]))
            print('start time change %s' % str(s[1]))
            t = restartProcess(t)
        elif value.startswith('x'):
            s = value.split()
            c.section_end_tweak(int(s[1]))
            print('end time change %s' % str(s[1]))
            t = restartProcess(t)
        elif value == 'q':
            try:
                # queue get 0 means the thread need to stop
                # print("putting 0 to queue")
                queue.put(0)
                # print("trying to join thread")
                insert_thread.join()
                # print("trying kill pg")
                os.killpg(os.getpgid(t.pid), signal.SIGTERM)
                # print("after kill pg")
            except Exception as e:
                print(e)
                os.kill(t.pid, signal.SIGTERM)
            break

