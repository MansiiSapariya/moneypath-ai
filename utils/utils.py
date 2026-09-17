def cn(*args):
    """
    Combine and merge CSS class names intelligently.
    Args:
        *args: List of class names or iterable of class names.
    Returns:
        String of class names separated by single spaces, without duplicates.
    """
    classes = []
    for arg in args:
        if isinstance(arg, str):
            classes.extend(arg.split())
        elif hasattr(arg, '__iter__'):
            for a in arg:
                if isinstance(a, str):
                    classes.extend(a.split())
    # Remove duplicates preserving order
    seen = set()
    result = []
    for cls in classes:
        if cls not in seen:
            seen.add(cls)
            result.append(cls)
    return ' '.join(result)
