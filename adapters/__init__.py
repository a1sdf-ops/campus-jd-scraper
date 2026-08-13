from .base import BaseAdapter, JobPost
from .bytedance import ByteDanceAdapter

ADAPTERS = {
    "bytedance": ByteDanceAdapter,
}
