try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version  # For Python <3.8

try:
    __version__ = version("chatterbox-tts")
except PackageNotFoundError:
    __version__ = "0.0.0+source"

def __getattr__(name):
    if name == "ChatterboxTTS":
        from .tts import ChatterboxTTS

        return ChatterboxTTS
    if name == "ChatterboxVC":
        from .vc import ChatterboxVC

        return ChatterboxVC
    if name in {"ChatterboxMultilingualTTS", "SUPPORTED_LANGUAGES"}:
        from .mtl_tts import ChatterboxMultilingualTTS, SUPPORTED_LANGUAGES

        return {
            "ChatterboxMultilingualTTS": ChatterboxMultilingualTTS,
            "SUPPORTED_LANGUAGES": SUPPORTED_LANGUAGES,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ChatterboxMultilingualTTS",
    "ChatterboxTTS",
    "ChatterboxVC",
    "SUPPORTED_LANGUAGES",
]
