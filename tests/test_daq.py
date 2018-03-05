import time
import logging

import pytest
from ophyd.status import wait as status_wait

from pcdsdaq import daq as daq_module
from pcdsdaq.daq import BEGIN_TIMEOUT

logger = logging.getLogger(__name__)


def test_connect(daq):
    """
    We expect connect to bring the daq from a disconnected state to a connected
    state.
    """
    logger.debug('test_connect')
    assert not daq.connected
    daq.connect()
    assert daq.connected
    daq.connect()  # Coverage
    # If something goes wrong...
    daq._control = None
    daq_module.pydaq = None
    daq.connect()
    assert daq._control is None


def test_disconnect(daq):
    """
    We expect disconnect to bring the daq from a connected state to a
    disconnected state.
    """
    logger.debug('test_disconnect')
    assert not daq.connected
    daq.connect()
    assert daq.connected
    daq.disconnect()
    assert not daq.connected


class Dummy:
    position = 4


def test_configure(daq, sig):
    """
    We expect the configured attribute to be correct.
    We expect a disconnected daq to connect and then configure.
    We expect a configure with no args to pick the defaults.
    We expect to be able to disconnect after a configure.
    We expect a connected daq to be able to configure.
    We expect configure to return both the old and new configurations.
    We expect read_configure to give us the current configuration, including
    default args.
    """
    logger.debug('test_configure')
    assert not daq.connected
    assert not daq.configured
    daq.configure()
    assert daq.config == daq.default_config
    assert daq.connected
    assert daq.configured
    daq.disconnect()
    assert not daq.connected
    assert not daq.configured
    daq.connect()
    assert daq.connected
    assert not daq.configured
    configs = [
        dict(events=1000, use_l3t=True),
        dict(events=1000, use_l3t=True, record=True),
        dict(duration=10, controls=dict(test=Dummy())),
    ]
    prev_config = daq.read_configuration()
    for config in configs:
        old, new = daq.configure(**config)
        assert old == prev_config
        assert daq.read_configuration() == new
        for key, value in config.items():
            assert daq.config[key] == value
        prev_config = daq.read_configuration()


def test_record(daq):
    """
    Make sure the record convenience method works.
    """
    logger.debug('test_record')
    daq.record()
    assert daq.config['record']
    daq.record(False)
    assert not daq.config['record']


@pytest.mark.timeout(10)
def test_basic_run(daq, sig):
    """
    We expect a begin without a configure to automatically configure
    We expect the daq to run for the time passed into begin
    We expect that we close the run upon calling end_run
    """
    logger.debug('test_basic_run')
    assert daq.state == 'Disconnected'
    daq.begin(duration=1, controls=[sig])
    assert daq.state == 'Running'
    time.sleep(1.3)
    assert daq.state == 'Open'
    daq.end_run()
    assert daq.state == 'Configured'
    daq.begin(events=1, wait=True, use_l3t=True)
    # now we force the kickoff to time out
    daq._control._state = 'Disconnected'
    start = time.time()
    status = daq.kickoff(duration=BEGIN_TIMEOUT+3)
    with pytest.raises(RuntimeError):
        status_wait(status, timeout=BEGIN_TIMEOUT+1)
    dt = time.time() - start
    assert dt < BEGIN_TIMEOUT + 1


@pytest.mark.timeout(3)
def test_stop_run(daq):
    """
    We expect the daq to run indefinitely if no time is passed to begin
    We expect that the running stops early if we call stop
    """
    logger.debug('test_stop_run')
    t0 = time.time()
    daq.begin()
    assert daq.state == 'Running'
    time.sleep(1.3)
    assert daq.state == 'Running'
    daq.stop()
    assert daq.state == 'Open'
    less_than_2 = time.time() - t0
    assert less_than_2 < 2


@pytest.mark.timeout(3)
def test_wait_run(daq):
    """
    We expect that wait will block the thread until the daq is no longer
    running
    We expect that a wait when nothing is happening will do nothing
    """
    logger.debug('test_wait_run')
    t0 = time.time()
    daq.wait()
    short_time = time.time() - t0
    assert short_time < 1
    t1 = time.time()
    daq.begin(duration=1)
    daq.wait()
    just_over_1 = time.time() - t1
    assert 1 < just_over_1 < 1.2
    t3 = time.time()
    daq.wait()
    short_time = time.time() - t3
    assert short_time < 1
    daq.end_run()


@pytest.mark.timeout(3)
def test_configured_run(daq, sig):
    """
    We expect begin() to run for the configured time, should a time be
    configured
    """
    logger.debug('test_configured_run')
    daq.configure(duration=1, controls=dict(sig=sig))
    t0 = time.time()
    daq.begin()
    daq.wait()
    just_over_1 = time.time() - t0
    assert 1 < just_over_1 < 1.2
    daq.end_run()


@pytest.mark.timeout(3)
def test_pause_resume(daq):
    """
    We expect pause and resume to work.
    """
    logger.debug('test_pause_resume')
    daq.begin(duration=5)
    assert daq.state == 'Running'
    daq.pause()
    assert daq.state == 'Open'
    daq.resume()
    assert daq.state == 'Running'
    daq.stop()
    assert daq.state == 'Open'
    daq.end_run()
    assert daq.state == 'Configured'


def test_check_connect(nodaq):
    """
    If the daq can't connect for any reason, we should get an error on any
    miscellaneous method that has the check_connect wrapper.
    """
    logger.debug('test_check_connect')
    with pytest.raises(RuntimeError):
        nodaq.wait()


def test_bad_stuff(daq, RE):
    """
    Miscellaneous exception raises
    """
    logger.debug('test_bad_stuff')

    # Bad mode name
    with pytest.raises(ValueError):
        daq.configure(mode='cashews')

    # Daq internal error
    configure = daq._control.configure
    daq._control.configure = None
    with pytest.raises(RuntimeError):
        daq.configure()
    daq._control.configure = configure

    # Run is too short
    with pytest.raises(RuntimeError):
        daq._check_duration(0.1)

    # Configure during a run
    daq.begin(duration=1)
    with pytest.raises(RuntimeError):
        daq.configure()
    daq.end_run()  # Prevent thread stalling


def test_call_everything_else(daq, sig):
    """
    These are things that bluesky uses. Let's check them.
    """
    logger.debug('test_call_everything_else')
    daq.describe_configuration()
    daq.configure(controls=dict(sig=sig))
    daq.stage()
    daq.unstage()
