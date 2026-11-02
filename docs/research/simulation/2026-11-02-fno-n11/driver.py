"""Import-once entry point, so Windows workers receive the research patches exactly once."""
import n11_lab

if __name__ == "__main__":
    n11_lab.main()
