# Copyright (c) 2013, Thomas P. Robitaille
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import (unicode_literals, division, print_function,
                        absolute_import)

import time
import argparse
import os


def get_percent(process):
    try:
        return process.cpu_percent()
    except AttributeError:
        return process.get_cpu_percent()


def get_memory(process):
    try:
        return process.memory_info()
    except AttributeError:
        return process.get_memory_info()


def all_children(pr):
    processes = []
    children = []
    try:
        children = pr.children()
    except AttributeError:
        children = pr.get_children()
    except Exception:  # pragma: no cover
        pass

    for child in children:
        processes.append(child)
        processes += all_children(child)
    return processes


def main():

    parser = argparse.ArgumentParser(
        description='(fork) Record CPU and memory usage for a process')

    parser.add_argument('process_id_or_command', type=str,
                        help='the process id or command')

    parser.add_argument('--log', type=str,
                        help='output the statistics to a file')

    parser.add_argument('--plot', type=str,
                        help='output the statistics to a plot')

    parser.add_argument('--duration', type=float,
                        help='how long to record for (in seconds). If not '
                             'specified, the recording is continuous until '
                             'the job exits.')

    parser.add_argument('--interval', type=float,
                        help='how long to wait between each sample (in '
                             'seconds). By default the process is sampled '
                             'as often as possible.')

    parser.add_argument('--include-children',
                        help='include sub-processes in statistics (results '
                             'in a slower maximum sampling rate).',
                        action='store_true')
    
    parser.add_argument('--include-io',
                        help='include I/O statistics',
                        action='store_true')
    
    parser.add_argument('--max-cpu-scale',
                        help='Use max CPU scale for multi-cores cpus',
                        action='store_true')

    args = parser.parse_args()

    # Attach to process
    try:
        pid = int(args.process_id_or_command)
        print("Attaching to process {0}".format(pid))
        sprocess = None
    except Exception:
        import subprocess
        command = args.process_id_or_command
        print("Starting up command '{0}' and attaching to process"
              .format(command))
        sprocess = subprocess.Popen(command, shell=True)
        pid = sprocess.pid

    monitor(pid, logfile=args.log, plot=args.plot, duration=args.duration,
            interval=args.interval, include_children=args.include_children, include_io=args.include_io, max_cpu_scale=args.max_cpu_scale)

    if sprocess is not None:
        sprocess.kill()


def monitor(pid, logfile=None, plot=None, duration=None, interval=None,
            include_children=False, include_io=True, max_cpu_scale=False):

    # We import psutil here so that the module can be imported even if psutil
    # is not present (for example if accessing the version)
    import psutil

    pr = psutil.Process(pid)

    # Record start time
    start_time = time.time()

    if logfile:
        f = open(logfile, 'w')
        f.write("# {0:12s} {1:12s} {2:12s} {3:12s}\n".format(
            'Elapsed time'.center(12),
            'CPU (%)'.center(12),
            'Real (MB)'.center(12),
            'Virtual (MB)'.center(12))
        )

    log = {}
    log['times'] = []
    log['cpu'] = []
    log['mem_real'] = []
    log['mem_virtual'] = []
    log['io'] = []
    log['io_read'] = []
    log['io_write'] = []

    try:

        # Start main event loop
        while True:

            # Find current time
            current_time = time.time()

            try:
                pr_status = pr.status()
            except TypeError:  # psutil < 2.0
                pr_status = pr.status
            except psutil.NoSuchProcess:  # pragma: no cover
                break

            # Check if process status indicates we should exit
            if pr_status in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                print("Process finished ({0:.2f} seconds)"
                      .format(current_time - start_time))
                break

            # Check if we have reached the maximum time
            if duration is not None and current_time - start_time > duration:
                break

            # Get current CPU and memory
            try:
                current_cpu = get_percent(pr)
                current_mem = get_memory(pr)
            except Exception:
                break
            current_mem_real = current_mem.rss / 1024. ** 2
            current_mem_virtual = current_mem.vms / 1024. ** 2

            # Get I/O information
            io_counters = pr.io_counters() 
            # Example: pio(read_count=686622, write_count=882937, read_bytes=93016064, write_bytes=613756928, read_chars=966944793, write_chars=655444485)
            current_io_read = io_counters[2] / 1024. ** 2
            current_io_write = io_counters[3] / 1024. ** 2
            # current_io = disk_usage_process / 1024.** 2  # mb
            
            # as % of total 
            # disk_usage_process = io_counters[2] + io_counters[3] # read_bytes + write_bytes
            # disk_io_counter = psutil.disk_io_counters()
            # disk_total = disk_io_counter[2] + disk_io_counter[3] # read_bytes + write_bytes
            # print("Disk", disk_usage_process/disk_total * 100)
            # current_io = disk_usage_process/disk_total * 100


            # Get information for children
            if include_children:
                for child in all_children(pr):
                    try:
                        current_cpu += get_percent(child)
                        current_mem = get_memory(child)
                    except Exception:
                        continue
                    current_mem_real += current_mem.rss / 1024. ** 2
                    current_mem_virtual += current_mem.vms / 1024. ** 2

            if logfile:
                f.write("{0:12.3f} {1:12.3f} {2:12.3f} {3:12.3f}\n".format(
                    current_time - start_time,
                    current_cpu,
                    current_mem_real,
                    current_mem_virtual))
                f.flush()

            if interval is not None:
                time.sleep(interval)

            # If plotting, record the values
            if plot:
                log['times'].append(current_time - start_time)
                log['cpu'].append(current_cpu)
                log['mem_real'].append(current_mem_real)
                log['mem_virtual'].append(current_mem_virtual)
                # log['io'].append(current_io)
                log['io_read'].append(current_io_read)
                log['io_write'].append(current_io_write)

    except KeyboardInterrupt:  # pragma: no cover
        pass

    if logfile:
        f.close()

    if plot:

        # Use non-interactive backend, to enable operation on headless machines
        import matplotlib.pyplot as plt

        with plt.rc_context({'backend': 'Agg'}):

            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1)

            ax.plot(log['times'], log['cpu'], '-', lw=1, color='r', label='CPU (%)')

            ax.set_ylabel('CPU (%)', color='r')
            ax.set_xlabel('time (s)')
            if max_cpu_scale:            
                #Only available in python 3
                #print("CPU count: %i"%os.cpu_count())
                cpu_count = int(os.cpu_count())
                ax.set_ylim(0., 100*cpu_count )
            else:
                # print("scale %f"%( max(log['cpu']) * 1.2) )
                ax.set_ylim(0., max(log['cpu']) * 1.2)


            if include_io:
                #memory + I/O
                ax3 = ax.twinx()
                ax3.plot(log['times'], log['mem_real'], '-', lw=1, color='b', label='RAM (MB)')
                ax3.plot(log['times'], log['io_read'], '-', lw=1, color='g', label='I/O Read')
                ax3.plot(log['times'], log['io_write'], '-', lw=1, color='m', label='I/O Write')
                ax3.set_ylim(0., max(max(log['mem_real']), max(log['io_read']), max(log['io_write'])) * 1.2)
                # ax3.set_ylabel('RAM (blue) - I/O read (green) - I/O write (magenta)] (MB)', color='k')
                ax3.set_ylabel('(MB)', color='k')
                # ax3.grid(True)
                ax3.legend(title="MB scale", fancybox=True)
                ax.legend(title="% scale", fancybox=True)
            else:
                #only memory
                ax2 = ax.twinx()
                ax2.plot(log['times'], log['mem_real'], '-', lw=1, color='b')
                ax2.set_ylim(0., max(log['mem_real']) * 1.2)
                ax2.set_ylabel('Real Memory (MB)', color='b')

            ax.grid()

            fig.savefig(plot)
