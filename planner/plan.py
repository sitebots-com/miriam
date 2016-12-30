import functools
import logging
import pickle

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm

from astar.astar_grid48con import astar_grid4con, distance_manhattan
from astar.base import NoPathException
from planner.base import astar_base

path_save = {}


def plan(agent_pos: list, jobs: list, alloc_jobs: list, idle_goals: list, grid: np.array, plot: bool = False,
         filename: str = 'path_save.pkl'):
    """
    Main entry point for planner

    Args:
      agent_pos: agent poses
      jobs: jobs to plan for (((s_x, s_y), (g_x, g_y), time), ((s_x ...), ..., time), ...)
        where time might be negative value if job is waiting
      alloc_jobs: preallocation of agent to a job (i.e. will travel to its goal)
      idle_goals: idle goals to consider (((g_x, g_y), (t_mu, t_std)), ...)
      grid: the map (2D-space + time)
      plot: whether to plot conditions and results or not
      filename: filename to save / read path_save (set to False to not do this)
      agent_pos: list: 
      jobs: list: 
      alloc_jobs: list: 
      idle_goals: list: 
      grid: np.array: 
      plot: bool:  (Default value = False)
      filename: str:  (Default value = 'path_save.pkl')

    Returns:
      : tuple of tuples of agent -> job allocations, agent -> idle goal allocations and blocked map areas

    """

    # load path_save
    if filename:  # TODO: check if file was created on same map
        global path_save
        try:
            with open(filename, 'rb') as f:
                path_save = pickle.load(f)
        except FileNotFoundError:
            logging.warning("WARN: File %s does not exist", filename)

    # result data structures
    agent_job = []
    for aj in alloc_jobs:
        agent_job.append(tuple(aj))
    agent_job = tuple(agent_job)
    _agent_idle = ()
    blocked = ()
    condition = comp2condition(agent_pos, jobs, alloc_jobs, idle_goals, grid)

    # planning!
    (agent_job, _agent_idle, blocked
     ) = astar_base(start=comp2state(agent_job, _agent_idle, blocked),
                    condition=condition,
                    goal_test=goal_test,
                    get_children=get_children,
                    heuristic=heuristic,
                    cost=cost)

    _paths = get_paths(condition, comp2state(agent_job, _agent_idle, blocked))

    # save path_save
    if filename:
        try:
            with open(filename, 'wb') as f:
                pickle.dump(path_save, f, pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            print(e)

    if plot:
        # Plot input conditions
        plt.style.use('bmh')
        fig = plt.figure()
        ax = fig.add_subplot(121)
        ax.set_aspect('equal')

        # Set grid lines to between the cells
        major_ticks = np.arange(0, len(grid[:, 0, 0]) + 1, 2)
        minor_ticks = np.arange(0, len(grid[:, 0, 0]) + 1, 1) + .5
        ax.set_xticks(major_ticks)
        ax.set_xticks(minor_ticks, minor=True)
        ax.set_yticks(major_ticks)
        ax.set_yticks(minor_ticks, minor=True)
        ax.grid(which='minor', alpha=0.5)
        ax.grid(which='major', alpha=0.2)

        # Make positive y pointing up
        ax.axis([-1, len(grid[:, 0]), -1, len(grid[:, 0])])

        # Show map
        plt.imshow(grid[:, :, 0] * -1, cmap="Greys", interpolation='nearest')
        # Agents
        agents = np.array(agent_pos)
        plt.scatter(agents[:, 0],
                    agents[:, 1],
                    s=np.full(agents.shape[0], 100),
                    color='blue',
                    alpha=.9)
        # Jobs
        for j in jobs:
            plt.arrow(x=j[0][0],
                      y=j[0][1],
                      dx=(j[1][0] - j[0][0]),
                      dy=(j[1][1] - j[0][1]),
                      head_width=.3, head_length=.7,
                      length_includes_head=True,
                      ec='r',
                      fill=False)
        # Idle Goals
        igs = []
        for ai in idle_goals:
            igs.append(ai[0])
        igs_array = np.array(igs)
        plt.scatter(igs_array[:, 0],
                    igs_array[:, 1],
                    s=np.full(igs_array.shape[0], 100),
                    color='g',
                    alpha=.9)

        # Legendary!
        plt.legend(["Agents", "Idle Goals"])
        plt.title("Problem Configuration and Solution")

        # plt.show()
        from mpl_toolkits.mplot3d import Axes3D
        _ = Axes3D
        ax3 = fig.add_subplot(122, projection='3d')
        ax3.axis([-1, len(grid[:, 0]), -1, len(grid[:, 0])])

        # plot agent -> job allocation
        for ajt in agent_job:
            for aj in ajt[1]:
                plt.arrow(x=agent_pos[ajt[0]][0],
                          y=agent_pos[ajt[0]][1],
                          dx=(jobs[aj][0][0] - agent_pos[ajt[0]][0]),
                          dy=(jobs[aj][0][1] - agent_pos[ajt[0]][1]),
                          ec='r',
                          fill=False,
                          linestyle='dotted')
        # plot agent -> idle goal allocations
        for ai in _agent_idle:
            plt.arrow(x=agent_pos[ai[0]][0],
                      y=agent_pos[ai[0]][1],
                      dx=(idle_goals[ai[1]][0][0] - agent_pos[ai[0]][0]),
                      dy=(idle_goals[ai[1]][0][1] - agent_pos[ai[0]][1]),
                      ec='g',
                      fill=False,
                      linestyle='dotted')

        # Paths
        legend_str = []
        i = 0

        for _pathset in _paths:  # pathset per agent
            for p in _pathset:
                pa = np.array(p)
                ax3.plot(xs=pa[:, 0],
                         ys=pa[:, 1],
                         zs=pa[:, 2])
                legend_str.append("Agent " + str(i))
            i += 1
        plt.legend(legend_str)

        plt.show()

    return agent_job, _agent_idle, _paths


# Main methods

def get_children(_condition: dict, _state: tuple) -> list:
    """
    Get all following states

    Args:
      _condition: The conditions of the problem
      _state: The parent state
    to be expanded

    Returns:
      : A list of children

    """
    (agent_pos, jobs, alloc_jobs, idle_goals, _) = condition2comp(_condition)
    (agent_job, _agent_idle, blocked) = state2comp(_state)
    (left_agent_pos, left_idle_goals, left_jobs
     ) = clear_set(_agent_idle, agent_job, agent_pos, idle_goals, jobs)

    eval_blocked = False
    for i in range(len(blocked)):
        if blocked[i][1].__class__ != int:  # two agents blocked
            eval_blocked = True
            break

    if eval_blocked:
        blocked1 = []
        blocked2 = []
        for i in range(len(blocked)):
            if blocked[i][1].__class__ != int:  # two agents blocked
                blocked1.append((blocked[i][0], blocked[i][1][0]))
                blocked2.append((blocked[i][0], blocked[i][1][1]))
            else:
                blocked1.append(blocked[i])
                blocked2.append(blocked[i])
        return [comp2state(agent_job, _agent_idle, tuple(blocked1)),
                comp2state(agent_job, _agent_idle, tuple(blocked2))]
    else:
        children = []
        agent_pos = list(agent_pos)
        agent_job = list(agent_job)
        jobs = list(jobs)
        idle_goals = list(idle_goals)
        if len(left_jobs) > 0:  # still jobs to assign - try with all left agents
            for left_job in left_jobs:  # this makes many children ... TODO: awesome heuristic!!
                job_to_assign = jobs.index(left_job)
                for a in range(len(agent_pos)):
                    has_assignment = False
                    agent_job_new = agent_job.copy()
                    for aj in agent_job:
                        if aj[0] == a:
                            has_assignment = True  # agent has an assignment
                            aj_new = (aj[0], tuple(aj[1]) + tuple([job_to_assign]))
                            aji = agent_job.index(aj)  # where to insert

                            agent_job_new[aji] = aj_new
                            children.append(comp2state(tuple(agent_job_new),
                                                       _agent_idle,
                                                       blocked))
                            break
                    if not has_assignment:
                        aj = (a, (job_to_assign,))
                        agent_job_new.append(aj)
                        children.append(comp2state(tuple(agent_job_new),
                                                   _agent_idle,
                                                   blocked))
            return children
        elif len(left_idle_goals) > 0:  # only idle goals to assign - try with all left agents
            for a in left_agent_pos:
                l = list(_agent_idle).copy()
                l.append((agent_pos.index(a),
                          idle_goals.index(left_idle_goals[0])))
                children.append(comp2state(tuple(agent_job),
                                           tuple(l),
                                           blocked))
            return children
        else:  # all assigned
            return []


def cost(_condition: dict, _state: tuple) -> float:
    """
    Get the cost increase for a change from _state1 to _state2

    Args:
      _condition: The conditions of the problem
      _state: The state to evaluate

    Returns:
      The **total** cost of this state
    """
    (agent_pos, jobs, alloc_jobs, idle_goals, _map) = condition2comp(_condition)
    (agent_job, _agent_idle, block_state) = state2comp(_state)
    _cost = 0.

    _paths = get_paths(_condition, _state)
    for i_agent in range(len(_paths)):
        pathset = list(_paths[i_agent])
        job_assignment = list(filter(lambda x: x[0] == i_agent, agent_job))
        if job_assignment:
            assert len(job_assignment) == 1, "Multiple agent entries"
            jobs = job_assignment[0][1]
            if (i_agent, jobs[0]) in alloc_jobs:  # first entry is a preallocated job
                assert len(pathset) % 2 == 1, "Must be odd number of paths"  # since first is one only
                for p in pathset[1::2]:
                    _cost += p[-1][2]
            else:
                assert len(pathset) % 2 == 0, "Must be even number of paths"
                for p in pathset[0::2]:
                    _cost += p[-1][2]  # each arrival time TODO: waiting time in job list
            break
        idle_assignment = list(filter(lambda x: x[0] == i_agent, _agent_idle))
        if idle_assignment:
            assert len(idle_assignment) == 1, "Multiple agent entries"
            i_idle_goal = idle_assignment[0][1]
            idle_goal_stat = idle_goals[i_idle_goal][1]
            path_len = pathset[0][-1][2]  # this agent will have only one path in its set, or has it?
            assert len(pathset) == 1, "an agent with idle goal must only have one path in its set"
            prob = norm.cdf(path_len, loc=idle_goal_stat[0], scale=idle_goal_stat[1])
            _cost += (prob * path_len)
            break

    # finding collisions in paths
    collision = find_collision(_paths)
    if collision != ():
        block_state += (collision,)
        _state = comp2state(agent_job, _agent_idle, block_state)
    return _cost, _state


def heuristic(_condition: dict, _state: tuple) -> float:
    """
    Estimation from this state to the goal

    Args:
      _condition: Input condition
      _state: State to eval

    Returns:
      cost heuristic for the given state
    """
    (agent_pos, jobs, alloc_jobs, idle_goals, _map) = condition2comp(_condition)
    (agent_job, _agent_idle, _) = state2comp(_state)
    _cost = 0.

    # what to assign
    n_jobs2assign = len(agent_pos) - len(agent_job)
    if n_jobs2assign == 0:
        return 0

    (agent_pos, idle_goals, jobs
     ) = clear_set(_agent_idle, agent_job, agent_pos, idle_goals, jobs)

    l = []
    for i_job in range(len(jobs)):
        j = jobs[i_job]
        for ja in alloc_jobs:
            if ja[1] == i_job:
                _cost += distance_manhattan(agent_pos[ja[0]], j[1])
                break
        else:
            p = path(j[0], j[1], _map, [], False)
            if p:  # if there was a path in the dict
                l.append(path_duration(p) ** 2)
            else:
                l.append(distance_manhattan(j[0], j[1]))
    l.sort()
    if len(l) > len(agent_pos):  # we assign only jobs
        for i_agent in range(len(agent_pos)):
            _cost += l[i_agent]
    else:  # we have to assign idle_goals, two
        for i_agent in range(len(agent_pos)):
            if i_agent < len(l):
                _cost += l[i_agent]
                # TODO: think about this part of the heuristic. Problem is: we don't know, which agent
    return _cost


def goal_test(_condition: dict, _state: tuple) -> bool:
    """
    Test if a state is the goal state regarding given conditions

    Args:
      _condition: Given conditions
      _state: State to check

    Returns:
      Result of the test (true if goal, else false)
    """
    (agent_pos, jobs, alloc_jobs, idle_goals, _) = condition2comp(_condition)
    (agent_job, _agent_idle, blocked) = state2comp(_state)
    agents_blocked = False
    for i in range(len(blocked)):
        if blocked[i][1].__class__ != int:  # two agents blocked
            agents_blocked = True
            break
    if len(agent_job) > 0:
        assigned_jobs = functools.reduce(lambda l, j: l + j[1], agent_job, tuple())
    else:
        assigned_jobs = ()
    return ((len(agent_pos) == len(agent_job) + len(_agent_idle)) and  # all agents have assignments
            len(assigned_jobs) == len(jobs) and  # all jobs are assigned
            not agents_blocked)


# Path Helpers

def clear_set(_agent_idle: tuple, agent_job: tuple, agent_pos: list, idle_goals: list, jobs: list) -> tuple:
    """
    Clear condition sets of agents, jobs and idle goals already assigned with each other

    Args:
      _agent_idle:
      agent_job:
      agent_pos:
      idle_goals:
      jobs:

    Returns:

    """
    cp_agent_pos = agent_pos.copy()
    cp_idle_goals = idle_goals.copy()
    cp_jobs = jobs.copy()

    for ajs in agent_job:
        cp_agent_pos.remove(agent_pos[ajs[0]])
        for j in ajs[1]:
            cp_jobs.remove(jobs[j])
    for ai in _agent_idle:
        cp_agent_pos.remove(agent_pos[ai[0]])
        cp_idle_goals.remove(idle_goals[ai[1]])
    return cp_agent_pos, cp_idle_goals, cp_jobs


def path(start: tuple, goal: tuple, _map: np.array, blocked: list, calc: bool = True) -> list:
    """
    Calculate or return pre-calculated path from start to goal

    Args:
      start: The start to start from
      goal: The goal to plan to
      _map: The map to plan on
      blocked: List of blocked points for agents e.g. ((x, y, t), agent)
      calc: whether or not the path should be calculated if no saved id available. (returns False if not saved)

    Returns:
      the path as list of tuples
      or [] if no path found
      or False if
    """
    index = tuple([start, goal]) + tuple(blocked)
    seen = set()
    if len(blocked) > 0:
        for b in blocked:
            _map = _map.copy()
            _map[(b[1],
                  b[0],
                  b[2])] = -1
            assert b not in seen, "Duplicate blocked entries"
            seen.add(b)

    if index not in path_save.keys():
        if calc:  # if we want to calc (i.e. find the cost)
            assert len(start) == 2, "Should be called with only spatial coords"
            try:
                _path = astar_grid4con((start + (0,)),
                                       (goal + (_map.shape[2] - 1,)),
                                       _map.swapaxes(0, 1))
            except NoPathException:
                _path = []

            path_save[index] = _path
        else:
            return False
    else:
        _path = path_save[index]

    # _path = _path.copy()
    for b in blocked:
        if b in _path:
            assert False, "Path still contains the collision"
    return _path


def path_duration(_path: list) -> int:
    """
    Measure the duration that the traveling of a path would take

    Args:
      _path: The path to measure

    Returns:
      The duration

    """
    return len(_path) - 1  # assuming all steps take one time unit


# Collision Helpers

def get_paths(_condition: dict, _state: tuple) -> list:
    """
    Get the path_save for a given state

    Args:
      _condition: Input condition
      _state:

    Returns:
      list of tuples per agent with all paths for this agent as lists of tuples of coords [([(..)])]
    """
    (agent_pos, jobs, alloc_jobs, idle_goals, _map) = condition2comp(_condition)
    (agent_job, _agent_idle, blocked) = state2comp(_state)
    _agent_idle = np.array(_agent_idle)
    _paths = []
    blocks = get_blocks_dict(blocked)
    for ia in range(len(agent_pos)):
        paths_for_agent = tuple()
        if ia in blocks.keys():
            block = blocks[ia]
        else:
            block = []
        for aj in agent_job:
            if aj[0] == ia:  # the agent we are looking for
                assigned_jobs = aj[1]
                pose = agent_pos[ia][0:2]
                t_shift = 0
                for job in assigned_jobs:
                    if (ia, job) in alloc_jobs:  # can be first only; need to go to goal only
                        p = path(pose, jobs[job][1], _map, block, calc=True)
                    else:
                        # trip to start
                        if len(paths_for_agent) > 0:
                            pose, t_shift = get_last_pose_and_t(paths_for_agent)
                        p1 = path(pose, jobs[job][0], _map, block, calc=True)
                        paths_for_agent += (timeshift_path(p1, t_shift),)
                        # start to goal
                        p1l = p1[-1][2]
                        block2 = []
                        for b in block:
                            if b[2] > p1l:
                                block2.append((b[0], b[1], b[2] - p1l))
                        _, t_shift = get_last_pose_and_t(paths_for_agent)
                        p = path(jobs[job][0], jobs[job][1], _map, block2, calc=True)
                    paths_for_agent += (timeshift_path(p, t_shift),)
                break  # for this agent
        for ai in _agent_idle:
            if ai[0] == ia:
                p = (path(agent_pos[ia], idle_goals[ai[1]][0], _map, block, calc=True))
                paths_for_agent += (p,)
                break  # found for this agent
        _paths.append(paths_for_agent)
    assert len(_paths) == len(agent_pos), "More or less paths than agents"
    return _paths


def get_last_pose_and_t(paths_for_agent, ):
    last = paths_for_agent[-1][-1]
    return last[0:2], last[2] + 1


def find_collision(_paths: list) -> tuple:
    """
    Find collisions in a set of path_save

    Args:
      _paths: set of path_save

    Returns:
      first found collision
    """
    from_agent = []
    all_paths = []
    ia = 0  # agent iterator
    seen = set()
    for _pathset in _paths:  # pathset per agent
        for _path in _pathset:
            for point in _path:
                if point in seen:  # collision
                    return tuple((point, (ia, from_agent[all_paths.index(point)])))
                seen.add(point)
                all_paths.append(point)
                from_agent.append(ia)
        ia += 1  # next path (of next agent)
    return ()


def concat_paths(path1: list, path2: list) -> list:
    """
    Append two paths to each other. Will keep timing of first path and assume second starts with t=0

    Args:
      path1: First path
      path2: Second path

    Returns:
      both paths after each other
    """
    assert path2[0][2] == 0, "Second path must start with t=0"

    if path1[-1][0:2] == path2[0][0:2]:
        path2.remove(path2[0])
    d = path1[-1][2]
    for i in range(len(path2)):
        path1.append((path2[i][0],
                      path2[i][1],
                      path2[i][2] + d))
    return path1


def timeshift_path(_path: list, t: int) -> list:
    """
    Shift a path to a certain time

    Args:
      _path: the path to shift
      t: time to shift by

    Returns:
      Shifted path
    """
    assert _path[0][2] == 0, "Input path should start at t=0"
    return list(map(lambda c: (c[0], c[1], c[2] + t), _path))


def get_blocks_dict(blocked):
    block_dict = {}
    for b in blocked:
        if b[1].__class__ == int:  # a block, not a conflict
            if b[1] in block_dict.keys():  # agent_nr
                block_dict[b[1]] += [b[0], ]
            else:
                block_dict[b[1]] = [b[0], ]
    return block_dict


def get_block_diff(agent, blocks1, blocks_new):
    if agent in blocks1.keys():
        block1 = blocks1[agent]
        block2 = blocks1[agent]
    else:
        block1 = []
        block2 = []
    if agent in blocks_new.keys():
        block2 += blocks_new[agent]
    return block1, block2


# Data Helpers

def condition2comp(_condition: dict):
    """
    Transform the condition dict to its components

    Args:
      _condition:

    Returns:

    """
    return (_condition["agent_pos"],
            _condition["jobs"],
            _condition["alloc_jobs"],
            _condition["idle_goals"],
            _condition["grid"])


def comp2condition(agent_pos: list,
                   jobs: list,
                   alloc_jobs: list,
                   idle_goals: list,
                   grid: np.array):
    """
    Transform condition sections into dict to use

    Args:
      agent_pos:
      jobs:
      alloc_jobs:
      idle_goals:
      grid:

    Returns:

    """
    return {
        "agent_pos": agent_pos,
        "jobs": jobs,
        "alloc_jobs": alloc_jobs,
        "idle_goals": idle_goals,
        "grid": grid
    }


def state2comp(_state: tuple) -> tuple:
    """
    Transform the state tuple to its components

    Args:
      _state:

    Returns:

    """
    return (_state[0],
            _state[1],
            _state[2])


def comp2state(agent_job: tuple,
               _agent_idle: tuple,
               blocked: tuple) -> tuple:
    """
    Transform state sections into tuple to use

    Args:
      agent_job: tuple: 
      _agent_idle: tuple:
      blocked: tuple: 

    Returns:

    """
    return agent_job, _agent_idle, blocked
