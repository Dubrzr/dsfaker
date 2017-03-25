import datetime
import time

import numpy

from dsfaker.exceptions import NotCompatibleGeneratorException
from dsfaker.listeners import CircularBuffer
from . import BoundedGenerator, Generator


class ConstantValueGenerator(Generator):
    def __init__(self, value, dtype: numpy.dtype):
        self.value = value
        self.dtype = dtype

    def _get_single(self) -> float:
        return self.value

    def _get_batch(self, batch_size: int) -> numpy.array:
        return numpy.ones(batch_size, dtype=self.dtype) * self.value


class BoundingOperator(BoundedGenerator):
    def __init__(self, generator: Generator, lb: float, ub: float):
        self.generator = generator
        self.lb = lb
        self.ub = ub

    def _get_single(self):
        return numpy.clip(self.generator.get_single(), self.lb, self.ub)

    def _get_batch(self, batch_size: int):
        return numpy.clip(self.generator.get_batch(batch_size=batch_size), self.lb, self.ub)


class ScalingOperator(BoundedGenerator):
    def __init__(self, generator: BoundedGenerator, lb: float, ub: float, dtype: numpy.dtype=None):
        if lb >= ub:
            raise ValueError("lb should be less than ub")

        if not isinstance(generator, BoundedGenerator):
            raise NotCompatibleGeneratorException("ScalingOperator needs a BoundedGenerator.")

        self.generator = generator
        self.lb = lb
        self.ub = ub
        self.mid = ub - (ub - lb) / 2
        self.gen_mid =  self.generator.ub - (self.generator.ub - self.generator.lb) / 2
        self.coef = (ub - lb) / (self.generator.ub - self.generator.lb)
        self.dtype = dtype

    def _get_single(self):
        return self.generator.get_single() * self.coef - (self.gen_mid * self.coef) + self.mid

    def _get_batch(self, batch_size: int):
        return numpy.asarray(self.generator.get_batch(batch_size=batch_size), dtype=self.dtype) * self.coef - (self.gen_mid * self.coef) + self.mid


class ApplyFunctionOperator(Generator):
    def __init__(self, function, generator: Generator):
        self.function = function
        self.generator = generator

    def _get_single(self) -> float:
        return self.function(self.generator.get_single())

    def _get_batch(self, batch_size: int) -> numpy.array:
        return self.function(self.generator.get_batch(batch_size=batch_size))


class AbsoluteOperator(ApplyFunctionOperator):
    def __init__(self, generator):
        super().__init__(numpy.absolute, generator)


class TimeDelayedGenerator(Generator):
    def __init__(self, generator: Generator, time_delay_sec: float=None, time_delay_generator: Generator=None):
        """
        The TimeDelayedGenerator gives a simple way to simulate a real application that returns data every 10 seconds for example.
        You can either provide the time delay between each values in seconds or via a generator.

        :param generator: the generator used to return values
        :param time_delay_ms: the time to sleep in seconds before returning the next value
        :param time_delay_generator: the time to sleep given by a generator in seconds before returning the next value
        """
        self.generator = generator
        self.time_delay_sec = time_delay_sec
        self.time_delay_generator = time_delay_generator

        self.start_time = None
        self.previous_time = None

    def _get_single(self) -> float:
        if self.time_delay_sec is not None:
            td = self.time_delay_sec
        else:
            td = self.time_delay_generator.get_single()
        td = datetime.timedelta(seconds=td)

        if self.start_time is None:
            self.start_time = datetime.datetime.now()
            self.previous_time = self.start_time
            return self.generator.get_single()

        while self.previous_time + td > datetime.datetime.now():
            time.sleep(((td.seconds + td.microseconds / 1000000) / 5))

        self.previous_time += td
        return self.generator.get_single()

    def _get_batch(self, batch_size: int) -> numpy.array:
        if self.time_delay_sec is not None:
            td = self.time_delay_sec * batch_size
        else:
            td = float(numpy.sum(self.time_delay_generator.get_batch(batch_size=batch_size)))
        td = datetime.timedelta(seconds=td)

        if self.start_time is None:
            self.start_time = datetime.datetime.now()
            self.previous_time = self.start_time

        while self.previous_time + td > datetime.datetime.now():
            time.sleep(((td.seconds + td.microseconds / 1000000) / 5))

        self.previous_time += td
        return self.generator.get_batch(batch_size=batch_size)


class CastOperator(Generator):
    def __init__(self, generator: Generator, dtype: numpy.dtype):
        self.generator = generator
        self.dtype = dtype

    def _get_single(self) -> float:
        return self.generator.get_single()

    def _get_batch(self, batch_size: int) -> numpy.array:
        return numpy.asarray(self.generator.get_batch(batch_size=batch_size), dtype=self.dtype)


class MeanHistory(Generator):
    def __init__(self, generator, size, initial_values=None):
        self.generator = generator
        self.history = CircularBuffer(size=size, initial_values=initial_values)

    def _get_single(self):
        mean = self.history.get_mean()
        self.history.put_single(self.generator.get_single())
        return mean
