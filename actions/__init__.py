"""SONIC AI Actions — all tool implementations.

Each module exposes a primary entry-point function that receives (action, params, ui)
and returns a string response.  Tools are dispatched from main.py via
``from actions.<module> import <function>``.
"""
