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
import kthread
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

        value = int(event.xdata)
        print("insert point:", value)
        self.c.insert(value)
        self.t_play.kill()
        

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
    
    def cmd_solver(self):
        while True:
            value = self.queue.get()
            print("Received cmd: ",value)
            if value == 'l':
                self.mode = 'play_loop'
                print('alter to loop mode')
                self.t_play.kill()
            elif value == 'o':
                self.mode = 'play_once'
                print('alter to once mode')
                self.t_play.kill()
            elif value == 'p':
                print('paint the wave')
                self.is_draw_wave = True
                self.t_play.kill()
            elif value == 'd':
                self.c.delete()
                print('delete a sentence')
                self.t_play.kill()
            elif value =='c':
                self.c.combine()
                print('conbine chunks')
                self.t_play.kill()
            elif value == 's':
                self.c.save()
                print('save chunks')
            elif value == 'n':
                self.c.next()
                self.t_play.kill()
                print('next sentence')
            elif value == 'b':
                self.c.pre()
                print('previous sentence')
                self.t_play.kill()
            elif value == 'q':
                try:
                    self.t_play.kill()
                    exit()
                except Exception as e:
                    print(e)
                break


    def play_thread(self):
        while(True):
            self.progress_start = datetime.now()
            play(self.sound[self.c.get_section_start():self.c.get_section_end()])

            if self.mode == "play_once":
                self.c.next()
            if self.mode == "play_loop":
                pass

    def play_chunks(self, queue:Queue):
        print("in play chunks: the main func of the child process")
        try:
            os.setsid()
        except:
            pass

        self.mode = "play_loop"
        self.c = Chunks()
        self.c.load()
        self.queue = queue
        self.is_draw_wave = False

        self.t_cmd_solver = threading.Thread(target=self.cmd_solver)
        self.t_cmd_solver.setDaemon(False)
        self.t_cmd_solver.start()
        
        print("cmd solver thread started")

        while True:
            self.t_play = kthread.KThread(target=self.play_thread)
            print("create a new thread")
            self.t_play.setDaemon(False)
            self.t_play.start()
            if self.is_draw_wave:
                self.draw_wave(self.c)
                self.is_draw_wave = False

            self.t_play.join()


        print('subprocess end')

if __name__ == "__main__":

    queue = Queue()
    play_process = PlayProcess()

    t = Process(target=play_process.play_chunks, args=(queue,))
    t.daemon = False
    t.start()

    print("Process started! Waiting for command!")
    while(True):
        value = input()
        queue.put(value)

