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


chunks = []
mode = "play_loop"
index = 0
length = 0
q = Queue()


class Chunk:
    def __init__(self, start, end):
        self.start = start
        self.end = end


def loadChunks():
    global chunks, length
    f = open("split.txt", "r")
    for i in f:
        (start, end) = i.split(" ")
        chunk = Chunk(int(start), int(end))
        chunks.append(chunk)
    length = len(chunks)


def saveChunks():
    f = open("split.txt", "w")
    for i in chunks:
        f.write("{0} {1}\n".format(i.start, i.end))


def genSplitFile():
    sound = AudioSegment.from_mp3("a.mp3")
    not_silence_ranges = detect_nonsilent(sound, 350, -36)
    keep_silence = 300

    sys.stdout = open("split.txt", "w")
    for start_i, end_i in not_silence_ranges:
        start_i = max(0, start_i - keep_silence)
        end_i += keep_silence
        print("{0} {1}".format(start_i, end_i))


def play_process(chunks, index, mode, q):
    # os.close(sys.stderr.fileno())
    sound = AudioSegment.from_mp3("a.mp3")
    try:
        os.setsid()
    except:
        pass

    def play_thread(index):
        length = len(chunks)
        while(True):
            chunk = chunks[index]
            play(sound[chunk.start:chunk.end])

            if mode == "play_once":
                index = (index + 1) % length
            if mode == "play_loop":
                pass

    t = threading.Thread(target=play_thread, args=(index,))
    t.setDaemon(False)
    t.start()
    t.join()
    # while(True):
    #     v = q.get()
    #     pid = os.getpid()
    #     print(v)
    #     if pid == v:
    #         break

    print('subprocess end')


if __name__ == "__main__":
    loadChunks()
    t = Process(target=play_process, args=(chunks, index, mode, q))
    t.daemon = False
    t.start()
    lastChunks = None

    def restartProcess():
        global t
        try:
            os.killpg(os.getpgid(t.pid), signal.SIGTERM)
        except:
            os.kill(t.pid, signal.SIGTERM)
        t = Process(target=play_process, args=(chunks, index, mode, q))
        t.start()

    while(True):
        value = input()
        if value == 'l':
            mode = 'play_loop'
            print('alter to loop mode')
            restartProcess()
        elif value == 'o':
            mode = 'play_once'
            print('alter to once mode')

            restartProcess()
        elif value == 'd':
            lastChunks = copy.deepcopy(chunks)
            del chunks[index]
            print('delete a sentence')

            restartProcess()
        elif value == 'r':
            if lastChunks:
                chunks = lastChunks
                print('resume chunks')
                restartProcess()
        elif value =='c':
            lastChunks = copy.deepcopy(chunks)
            try:
                chunks[index].end = chunks[index+1].end
                del chunks[index+1]
            except:
                print('fail to conbine')
            print('conbine chunks')
            restartProcess()

        elif value == 's':
            saveChunks()
            print('save chunks')
        elif value == 'n':
            length = len(chunks)
            index = (index + 1) % length
            restartProcess()
            print('next sentence')

        elif value == 'b':
            if index==0:
                continue
            index = (index - 1) % length
            print('previous sentence')

            restartProcess()
        elif value.startswith('z'):
            s = value.split()
            try:
                chunks[index].start+=int(s[1])
                print('start time change %s' % str(s[1]))
            except:
                pass
            restartProcess()

        elif value.startswith('x'):
            s = value.split()
            try:
                chunks[index].end+=int(s[1])
                print('end time change %s' % str(s[1]))
            except:
                pass
            restartProcess()

        elif value == 'q':
            try:
                os.killpg(os.getpgid(t.pid), signal.SIGTERM)
            except:
                os.kill(t.pid, signal.SIGTERM)
            break

