#!/usr/bin/python

import logging
import threading
from datetime import datetime
from time import sleep

import numpy as np

from planner.mod_cbsextension import Cbsext
from planner.mod_random import Random
from planner.process_sim.product import Product
from planner.process_sim.station import Station
from planner.simulation import SimpSim

FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(format=FORMAT, level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.WARN)


class Transport_Handler(object):
    stations = []
    flow = []
    product_list = []

    def __init__(self, n_products=10):
        self.n_products = n_products
        self.lade_Listen()

    def start(self, n=10, sim_thread=None):
        Product.sim_thread = sim_thread
        Station.sim_thread = sim_thread

        print("Simulation startet:")
        t_start = datetime.now()

        for i in range(0, n):
            t = threading.Thread(target=Product, args=(self, self.stations, self.flow, i)).start()
            # self.product_list.append(t)
        sleep(0.1 * n)

        # print("Product :",self.product_list)
        are_products_finished = False
        while (are_products_finished == False):
            is_done = True
            for prod in self.product_list:
                if (not prod.is_finished()):
                    is_done = False
            if (is_done):
                are_products_finished = True
                print("it's done, magic")
            sleep(0.1)

        t_end = datetime.now()
        t_dt = (t_end - t_start).total_seconds()
        print("Der Vorgang mit", n, "Produkten dauerte", t_dt, "sekunden.")
        return t_dt

    def register_products(self, prod=Product):
        self.product_list.append(prod)
        # print("Product was added, size:",self.product_list.__len__())

    def lade_Listen(self):
        # Import Stations, flow and Products from XML
        # If File exists
        if (False):
            pass
        else:
            self.stations = [
                Station("Lager", [0, 0]),
                Station("Trennen", [9, 9]),
                Station("Bohren", [4, 0]),
                Station("Fuegen", [4, 9]),
                Station("Schweißen", [0, 9]),
                Station("Polieren", [0, 4]),
                Station("Ausgang", [9, 4]),
            ]
            a = Station("a")
            self.flow = [[0, 2],
                         [1, 3],
                         [2, 1],
                         [4, 4],
                         [3, 3],
                         [5, 3],
                         [6, 2]
                         ]
            print("Keine XML gefunden, lade Ersatzwerte", self.flow)

_map = np.zeros([10, 10, 51])

def test_process_Random():
    mod = Random(_map)
    t = run_with_module(mod)
    return t


def test_process_Cbsext():
    mod = Cbsext(_map)
    t = run_with_module(mod)
    return t


def run_with_module(mod):
    agv_sim = SimpSim(False, mod)
    agv_sim.start()
    agv_sim.start_sim(20, 20, 3)
    start_object = Transport_Handler()
    n = start_object.start(5, agv_sim)
    agv_sim.stop()
    return n


if __name__ == "__main__":
    t_random = test_process_Random()
    t_cbsext = test_process_Cbsext()
    print("Random:", str(t_random),
          "\nCbsExt:", str(t_cbsext))
