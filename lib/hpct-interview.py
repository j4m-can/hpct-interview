#! /usr/bin/env python3
#
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# lib/hpct-interview.py

import json
import os.path
import sys
import yaml

from hpctinterview.interview import Interview


def print_usage():
    progname = os.path.basename(sys.argv[0])
    print(
        f"""usage: {progname} [-q] [-o <output>] <interviewfile> [<answersfile> [<resultsfile>]]

Run the interview as stored in <interviewfile>. The <answersfile>
should contain answer lines ("answer: <answer>") for each interaction
required in the interview. The <resultsfile> should contain the
expected settings/results of the interview.

If a <resultsfile> is provided, a report will be provided comparing
it with the results of the interview just done."""
    )


if __name__ == "__main__":
    try:
        answers_filename = None
        interview_filename = None
        output_filename = None
        results_filename = None
        verbose = False

        args = sys.argv[1:]

        while args:
            arg = args.pop(0)

            if arg in ["-h", "--help"]:
                print_usage()
                sys.exit(0)
            elif arg == "-o":
                output_filename = args.pop(0)
            elif arg == "-q":
                verbose = False
            elif arg.startswith("-"):
                break
            else:
                interview_filename = arg

                if args:
                    answers_filename = args.pop(0)

                if args:
                    results_filename = args.pop(0)

                break

        if args or interview_filename == None:
            raise Exception("bad/missing arguments")
    except SystemExit:
        raise
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)

    if 0:
        try:
            interview = Interview()
            interview.load(interview_filename)
            interview.check()
            print("passed")
        except:
            raise

    interview_home = os.path.dirname(os.path.realpath(interview_filename))

    interview = Interview(home=interview_home)
    interview.load(interview_filename)

    if answers_filename:
        answers = [s.strip() for s in open(answers_filename, "r").readlines()]
    else:
        answers = None
    interview.test(answers=answers, verbose=verbose)

    if results_filename:
        results = json.load(open(results_filename, "r"))
        interview.compare_results(results)

    if output_filename:
        yaml.dump(interview._settings, open(output_filename, "w"))
