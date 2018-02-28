from pydub import AudioSegment
from pydub.silence import split_on_silence
from pydub.silence import detect_nonsilent
from pydub.playback import play
import copy
import sys
import threading
import contextlib
import signal
import os
from multiprocessing import Process, Value, Array, Queue



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

class PlayProcess(object):
    def __init__(self):
        fileName = sys.argv[1]
        self.sound = AudioSegment.from_mp3(fileName)
    def play_chunks(self, chunks:Chunks, mode):
        try:
            os.setsid()
        except:
            pass

        def play_thread():
            while(True):
                play(self.sound[chunks.get_section_start():chunks.get_section_end()])

                if mode == "play_once":
                    chunks.next()
                if mode == "play_loop":
                    pass

        t = threading.Thread(target=play_thread)
        t.setDaemon(False)
        t.start()
        t.join()

        print('subprocess end')

if __name__ == "__main__":
    mode = "play_loop"

    c = Chunks()
    c.load()
    play_process = PlayProcess()

    t = Process(target=play_process.play_chunks, args=(copy.deepcopy(c),mode))
    t.daemon = False
    t.start()
    lastChunks = None

    def restartProcess(t):
        try:
            os.killpg(os.getpgid(t.pid), signal.SIGTERM)
        except:
            os.kill(t.pid, signal.SIGTERM)
        t = Process(target=play_process.play_chunks, args=(copy.deepcopy(c), mode))
        t.start()
        return t

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
                os.killpg(os.getpgid(t.pid), signal.SIGTERM)
            except:
                os.kill(t.pid, signal.SIGTERM)
            break

