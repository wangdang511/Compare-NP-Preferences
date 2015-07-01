'''Script to generate a summary PDF for each site in NP showing: 
    logoplots for replicate measurements, 
    logoplots for average prefs,
    and site identity in both strains.

    Run with two arguments at the command line:
    1st, the directory containing preference files (should be the dms_tools output directory)
    2nd, an output directory for the summary pdfs generated by this script
'''

import rmsdtools
import sitegroups
import os
import sys
import string
import time
import multiprocessing
import glob


def RunScript(rundir, run_name, script_name, commands, use_sbatch, sbatch_cpus, walltime=None, use_full_partition=False):
    """Runs a script with specified command-line options.

    This function was originally written by Jesse Bloom; I have modified it to 
    run scripts with command-line arguments (eg those taken by dms_tools) instead 
    of infiles (eg those taken by mapmuts). - Mike Doud

    *rundir* is the directory in which we run the job. Created if it does
    not exist.
    *run_name* is the name of the run, which should be a string without
    spaces.
    *script_name* is the name of the script that we run.
    *commands* is a list of commands for the script (command-line arguments).
    *use_sbatch* is a Boolean switch specifying whether we use ``sbatch``
    to run the script. If *False*, the script is just run with the command
    line instruction. If *True*, then ``sbatch`` is used, and the command file
    has the prefix *run_name* followed by the suffix ``.sbatch``.
    *sbatch_cpus* is an option that is only meaningful if *use_sbatch* is 
    *True*. It gives the integer number of CPUs that are claimed via
    ``sbatch`` using the option ``sbatch -c``. 
    *waltime* is an option that is only meaningful if *use_sbatch* is
    *True*. If so, it should be an integer giving the number of hours 
    to allocate for the job. If *walltime* has its default value of 
    *None*, no wall time for the job is specified.
    It is assumed that the script can be run at the command line using::
        script_name (command-line options)
    Returns *runfailed*: *True* if run failed, and *False* otherwise.
    """


    print "Running %s for %s in directory %s..." % (script_name, run_name, rundir)
    currdir = os.getcwd()
    if not os.path.isdir(rundir):
        os.mkdir(rundir)
    os.chdir(rundir)

    if (not run_name) or not all([x not in string.whitespace for x in run_name]):
        raise ValueError("Invalid run_name of %s" % run_name)

    if use_sbatch:
        sbatchfile = '%s.sbatch' % run_name # sbatch command file
        jobidfile = 'sbatch_%s_jobid' % run_name # holds sbatch job id
        jobstatusfile = 'sbatch_%s_jobstatus' % run_name # holds sbatch job status
        joberrorsfile = 'sbatch_%s_errors' % run_name # holds sbatch job errors
        sbatch_f = open(sbatchfile, 'w')
        sbatch_f.write('#!/bin/sh\n#SBATCH\n')
        if walltime:
            sbatch_f.write('#PBS -l walltime=%d:00:00\n' % walltime)


        sbatch_f.write('%s ' % (script_name))
        for command in commands:
            sbatch_f.write('%s ' % command)
        sbatch_f.close()

        if use_full_partition:
            os.system('sbatch -c %d -p full -e %s %s > %s' % (sbatch_cpus, joberrorsfile, sbatchfile, jobidfile))
        else:
            os.system('sbatch -c %d -e %s %s > %s' % (sbatch_cpus, joberrorsfile, sbatchfile, jobidfile))

        time.sleep(10) # short 20 sec delay
        jobid = int(open(jobidfile).read().split()[-1])
        nslurmfails = 0
        while True:
            time.sleep(5) # delay 5 sec
            returncode = os.system('squeue -j %d > %s' % (jobid, jobstatusfile))
            if returncode != 0:
                nslurmfails += 1
                if nslurmfails > 1000: # error if squeue fails at least 180 consecutive times
                    raise ValueError("squeue is continually failing, which means that slurm is not working on your system. Note that although this script has crashed, many of the jobs submitted via slurm may still be running. You'll want to monitor (squeue) or kill them (scancel) -- unfortunately you can't do that until slurm starts working again.")
                continue # we got an error while trying to run squeue
            nslurmfails = 0
            lines = open(jobstatusfile).readlines()
            if len(lines) < 2:
                break # no longer in slurm queue
        errors = open(joberrorsfile).read().strip()
    

    else: 
        full_command = '%s ' % (script_name) + ' '.join(commands)
        errors = os.system(full_command)


    os.chdir(currdir)
    if errors:
        print "ERROR running %s for %s in directory %s." % (script_name, run_name, rundir)
        return True
    else:
        print "Successfully completed running %s for %s in directory %s." % (script_name, run_name, rundir)
        return False


def RunProcesses(processes, nmultiruns):
    """Runs a list *multiprocessing.Process* processes.
    *processes* is a list of *multiprocessing.Process* objects that
    have not yet been started.
    *nmultiruns* is an integer >= 1 indicating the number of simultaneous
    processes to run.
    Runs the processes in *processes*, making sure to never have more than
    *nmultiruns* running at a time. If any of the processes fail (return
    an exitcode with a boolean value other than *False*), an exception
    is raised immediately. Otherwise, this function finishes when all
    processes have completed.
    """
    if not (nmultiruns >= 1 and isinstance(nmultiruns, int)):
        raise ValueError("nmultiruns must be an integer >= 1")
    processes_started = [False] * len(processes)
    processes_running = [False] * len(processes)
    processes_finished = [False] * len(processes)
    while not all(processes_finished):
        if (processes_running.count(True) < nmultiruns) and not all(processes_started):
            i = processes_started.index(False)
            processes[i].start()
            processes_started[i] = True
            processes_running[i] = True
        for i in range(len(processes)):
            if processes_running[i]:
                if not processes[i].is_alive():
                    processes_running[i] = False
                    processes_finished[i] = True
                    if processes[i].exitcode:
                        raise IOError("One of the processes failed to complete.")
        time.sleep(5)


def MakeSiteSummaryFigure(site, output_dir):
    texfile_name = output_dir + '/intermediates/site_%d_summary.tex' % site
    tex_file_out = open(texfile_name, 'w')
    tex_file_out.write('\documentclass[12pt]{article}\n')
    tex_file_out.write('\usepackage[parfill]{parskip}\n')
    tex_file_out.write('\usepackage{graphicx}\n')
    tex_file_out.write('\usepackage{amssymb}\n')
    tex_file_out.write('\usepackage{epstopdf}\n')
    tex_file_out.write('\DeclareGraphicsRule{.tif}{png}{.png}{`convert #1 `dirname #1`/`basename #1 .tif`.png}\n')
    tex_file_out.write('\usepackage{color}\n')
    tex_file_out.write('\pagestyle{empty}\n')
    tex_file_out.write('\\renewcommand{\\familydefault}{\sfdefault}\n')
    tex_file_out.write('\usepackage[paperheight=2in,paperwidth=4in,top=0in,bottom=0in,right=0in,left=0in]{geometry}\n')
    tex_file_out.write('\\begin{document}\n')
    tex_file_out.write('\\begin{figure}\n')
    tex_file_out.write('\\begin{picture}(10, 10)\n')
    tex_file_out.write('\put(110,25){site %d}\n' % site)
    tex_file_out.write('\put(40,8){PR/1934}\n')
    tex_file_out.write('\put(160,8){Aichi/1968}\n')
    tex_file_out.write('\linethickness{2pt}\n')
    tex_file_out.write('\put(25,5){\line(1,0){66}}\n')
    tex_file_out.write('\put(101,5){\line(1,0){160}}\n')
    tex_file_out.write('\put(80 ,-6){$\overline\pi$}\n')
    tex_file_out.write('\put(103 ,-6){$\overline\pi$}\n')
    tex_file_out.write('\put(30,-90){wildtype:}\n')
    tex_file_out.write('\put(80,-90){%s}\n' % sitegroups.pr8_identity(site))
    tex_file_out.write('\put(103,-90){%s}\n' % sitegroups.aichi68_identity(site))
    tex_file_out.write('\end{picture}\n')
    tex_file_out.write('\n')
    tex_file_out.write('\centerline{\hspace{0in}\n')
    tex_file_out.write('%[trim=left bottom right top, clip]\n')
    tex_file_out.write('\includegraphics[height=1in, trim=0 12 10 0, clip]{PR8replicates_site_%d_replicatemeasurements.pdf}\n' % site)
    tex_file_out.write('\includegraphics[height=1in, trim=0 12 10 0, clip]{PR8mean_site_%d_replicatemeasurements.pdf}\n' % site)
    tex_file_out.write('\includegraphics[height=1in, trim=0 12 10 0, clip]{AICHImean_site_%d_replicatemeasurements.pdf}\n' % site)
    tex_file_out.write('\includegraphics[height=1in, trim=0 12 10 0, clip]{AICHIreplicates_site_%d_replicatemeasurements.pdf}\n' % site)
    tex_file_out.write('}\n')
    tex_file_out.write('\end{figure}\n')
    tex_file_out.write('\end{document}\n')
    tex_file_out.close()

    # compile the tex to pdf
    RunScript(output_dir+'/intermediates/', 'pdf-%d' % site, 'pdflatex', [texfile_name, '-output-directory', outputdir], False, 1)


###################################################################################


sites = range(2,499)

pref_files_dir = sys.argv[1]

output_dir = sys.argv[2]
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)

intermediates_dir = output_dir + '/intermediates/'
if not os.path.isdir(intermediates_dir):
    os.mkdir(intermediates_dir)

#=====
# Make all the replicate logoplots and mean logoplots for each site.

# 1. three replicates of PR8
pr8_replicate_prefs = [pref_files_dir + '/' + 'PR8_replicate_%d_prefs.txt' % i for i in range(1,4)]
# 2. ten replicates of Aichi (with C1 and C2 at the end...)
aichi_replicate_prefs = [pref_files_dir + '/' + 'Aichi68A_replicate_%d_prefs.txt' % i for i in range(1,5)] + \
                        [pref_files_dir + '/' + 'Aichi68B_replicate_%d_prefs.txt' % i for i in range(1,5)] + \
                        [pref_files_dir + '/' + 'Aichi68C_replicate_%d_prefs.txt' % i for i in range(1,3)]
# 3. One average of PR8
pr8_mean_prefs = pref_files_dir + '/' + 'PR8_mean_prefs.txt'
# 4. One average of Aichi
aichi_mean_prefs = pref_files_dir + '/' + 'mean_Aichi68_both_studies_prefs.txt'

rmsdtools.WriteReplicateMeasurementPrefs(pr8_replicate_prefs, sites, outputdir=intermediates_dir, fileprefix='PR8replicates')
rmsdtools.WriteReplicateMeasurementPrefs(aichi_replicate_prefs, sites, outputdir=intermediates_dir, fileprefix='AICHIreplicates')
rmsdtools.WriteReplicateMeasurementPrefs([pr8_mean_prefs], sites, outputdir=intermediates_dir, fileprefix='PR8mean')
rmsdtools.WriteReplicateMeasurementPrefs([aichi_mean_prefs], sites, outputdir=intermediates_dir, fileprefix='AICHImean')

logos_to_make = glob.glob('%s/*_site_*replicatemeasurements.txt' % intermediates_dir)
processes = []
for i,f in enumerate(logos_to_make):
    outfile = f[f.rfind('/')+1:].rstrip('.txt') + '.pdf'
    commands = [f,outfile]
    if not os.path.isfile(intermediates_dir+'/'+outfile):
        processes.append(multiprocessing.Process(target=RunScript,\
            args=(intermediates_dir, "logo%d" % i, 'dms_logoplot', commands, True, 12)))

RunProcesses(processes, nmultiruns=100)


# generate latex files and compile pdfs:
for site in sites:
    MakeSiteSummaryFigure(site, output_dir)


